#!/usr/bin/env python3

import argparse
import datetime
import json
import re
from json import JSONEncoder
import logging
import os
import sys
from types import SimpleNamespace
from urllib.request import urlopen
from urllib.parse import urlparse
import uuid

import boto3
from botocore.exceptions import ClientError

logger = logging.Logger('envoi-transcribe-translate')

DEFAULT_TRANSCRIPTION_OUTPUT_FOLDER_NAME = 'transcribed'
DEFAULT_TRANSCRIPTION_SOURCE_LANGUAGE_CODE = None
DEFAULT_TRANSCRIPTION_SUBTITLE_FORMATS = ['srt', 'vtt']
DEFAULT_TRANSCRIPTION_AUTO_IDENTIFY_SOURCE_LANGUAGE = False
DEFAULT_TRANSCRIPTION_CREATE_DEFAULT_JOB_NAME = True

DEFAULT_TRANSLATION_OUTPUT_FOLDER_NAME = 'translated'
DEFAULT_TRANSLATION_SOURCE_LANGUAGE_CODE = 'auto'


class CustomJsonEncoder(JSONEncoder):

    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.isoformat()
        if isinstance(o, uuid.UUID):
            return str(o)
        return JSONEncoder.default(self, o)


class StorageHelper:

    @classmethod
    def read_file(cls, file_path):
        if file_path.startswith('s3://'):
            bucket_name, object_key = parse_s3_uri(file_path)
            return S3Helper().read_object(bucket_name=bucket_name, object_key=object_key)
        elif file_path.startswith('http'):
            return urlopen(file_path).read()
        else:
            with open(file_path) as f:
                return f.read()

    @classmethod
    def read_file_json(cls, file_path):
        file_contents = cls.read_file(file_path)
        return json.loads(file_contents) if file_contents is not None else None


class S3Helper:

    def __init__(self, client=None):
        self.s3 = client or boto3.client('s3')

    def read_object(self, bucket_name, object_key):
        try:
            response = self.s3.get_object(Bucket=bucket_name, Key=object_key)
            return response['Body'].read().decode('utf-8')
        except ClientError as e:
            if e.response['Error']['Code'] == "404":
                return None
            else:
                raise e

    def read_object_json(self, bucket, key):
        file_contents = self.read_object(bucket, key)
        return json.loads(file_contents) if file_contents is not None else None


class EnvoiTranscribeTranslateCreateCommand:

    def __init__(self, opts):
        self.opts = opts

    def run(self, opts=None):
        if opts is None:
            opts = self.opts

        run_input = build_run_input(opts)
        is_dry_run = getattr(opts, 'dry_run', False)
        if is_dry_run:
            print(json.dumps(run_input, indent=2))
        else:
            execution_arn = run_step_function(opts.state_machine_arn, run_input)
            print(execution_arn)

    @classmethod
    def init_parser(cls, subparsers=None, command_name="create"):
        if subparsers is None:
            parser = argparse.ArgumentParser()
        else:
            parser = subparsers.add_parser(
                command_name,
                help="Create a new state machine execution.",
            )
        parser.set_defaults(handler=cls)
        parser.add_argument('--media-file-uri', dest='media_file_uri',
                            required=True,
                            help='The S3 URI of the media file to transcribe.')
        parser.add_argument('--auto-identify-source-language', dest='auto_identify_source_language',
                            action='store_true',
                            help='Tells transcribe to try and automatically identify the source language of the '
                                 'media file.')
        parser.add_argument('--create-default-transcription-job-name',
                            dest='create_default_transcription_job_name',
                            action='store_true',
                            default=DEFAULT_TRANSCRIPTION_CREATE_DEFAULT_JOB_NAME,
                            help='Tells transcribe to create a default job name. The default job name will consist of '
                                 '{media_file_name_without_extension}-{source_language}')
        parser.add_argument('--state-machine-arn', dest='state_machine_arn',
                            help='The ARN of the state machine to run.')
        parser.add_argument("--log-level", dest="log_level",
                            default="WARNING",
                            help="Set the logging level (options: DEBUG, INFO, WARNING, ERROR, CRITICAL)")
        parser.add_argument('--dry-run', dest='dry_run',
                            action='store_true',
                            help='Do not run the state machine, just print the input.')
        parser.add_argument('--output-bucket-name', dest='output_bucket_name',
                            default=None,
                            help='A default bucket for file output. This will be used if a more specific S3 URI is '
                                 '\n not supplied. ex: --output-s3-uri, --transcription-output-s3-uri, '
                                 '--translation-output-s3-uri')
        parser.add_argument('--output-s3-uri', dest='output_s3_uri',
                            default=None,
                            help='A default S3 URI for file output. This will be used if a more specific S3 URI is '
                                 '\n not supplied. ex: --transcription-output-s3-uri, --translation-output-s3-uri')

        # Transcription options
        parser.add_argument('--transcription-job-name', dest='transcription_job_name',
                            default=None,
                            help='The name of the job.')
        parser.add_argument('--transcription-output-folder-name', dest='transcription_output_folder_name',
                            default=DEFAULT_TRANSCRIPTION_OUTPUT_FOLDER_NAME,
                            help='The name of the folder in the S3 bucket where the transcribed files are stored.')
        parser.add_argument('--transcription-output-s3-uri', dest='transcription_output_s3_uri',
                            default=None,
                            help='The S3 URI of the translate output file location.')
        parser.add_argument('--transcription-source-language-code', dest='transcription_source_language_code',
                            default=DEFAULT_TRANSCRIPTION_SOURCE_LANGUAGE_CODE,
                            help='The language of the source file.')

        # Translation options
        parser.add_argument('--translation-data-access-role-arn', dest='translation_data_access_role_arn',
                            default=None,
                            help='The ARN of the role to use for translate to access data.')
        parser.add_argument('-l', '--translation-languages', dest='translation_language_codes',
                            nargs="+",
                            help='The languages to translate to.')
        parser.add_argument('--translation-output-folder-name', dest='translation_output_folder_name',
                            default=DEFAULT_TRANSLATION_OUTPUT_FOLDER_NAME,
                            help='The name of the folder in the S3 bucket where the translated files are stored.')
        parser.add_argument('--translation-output-s3-uri', dest='translation_output_s3_uri',
                            default=None,
                            help='The S3 URI of the translate output file location.')
        parser.add_argument('--translation-source-language-code', dest='translation_source_language_code',
                            default=DEFAULT_TRANSLATION_SOURCE_LANGUAGE_CODE,
                            help='The language of the source file.')
        return parser


class EnvoiTranscribeTranslateDescribeCommand:

    def __init__(self, opts=None):
        self.opts = opts

    def run(self, opts=None):
        if opts is None:
            opts = self.opts

        execution_arn = opts.execution_arn
        sme = StateMachineExecution(execution_arn=execution_arn)
        description = sme.describe()
        logger.debug("Description: %s", description)

        input_as_string = description.get('input', None)
        output_as_string = description.get('output', None)

        if input_as_string is not None:
            input_as_json = json.loads(input_as_string)
            description['input'] = input_as_json
            # print(json.dumps(input_as_json, indent=2))

        output_as_json = None
        if output_as_string is not None:
            output_as_json = json.loads(output_as_string)
            description['output'] = output_as_json
            # print(json.dumps(output_as_json, indent=2))

        if opts.uris_only:
            transcription_job = output_as_json.get('TranscriptionJob', {})
            subtitles = transcription_job.get('Subtitles', {})
            sub_title_file_urls = subtitles.get('SubtitleFileUris', None)

            transcript = transcription_job.get('Transcript', None)
            transcript_uri = transcript.get('TranscriptFileUri', None)

            output = {
                "Transcription": {
                    "TranscriptFileUri": transcript_uri,
                    "SubtitleFileUris": sub_title_file_urls
                }
            }
            print(json.dumps(output, indent=2))

        else:
            print(json.dumps(json.loads(CustomJsonEncoder().encode(description)), indent=2))

    @classmethod
    def init_parser(cls, subparsers=None, command_name="describe"):
        if subparsers is None:
            parser = argparse.ArgumentParser()
        else:
            parser = subparsers.add_parser(
                command_name,
                help="Describe an execution.",
            )
        parser.set_defaults(handler=cls)
        parser.add_argument(
            "--execution-arn",
            action="store",
            dest="execution_arn",
            default=None,
            help="The ARN of the state machine execution to describe.",
        )
        parser.add_argument(
            "--uris-only",
            action="store_true",
            dest="uris_only",
            default=False,
            help="Only print the URIs of the output files."
        )

        return parser


class EnvoiTranscribeTranslateCommand:

    def __init__(self):
        pass

    @classmethod
    def init_parser(cls, subparsers=None, command_name="transcribe-translate"):
        if subparsers is None:
            parser = argparse.ArgumentParser()
        else:
            parser = subparsers.add_parser(
                command_name,
                help="Interact with Transcode-Translate jobs.",
            )

        sub_commands = {
            'create': EnvoiTranscribeTranslateCreateCommand,
            'describe': EnvoiTranscribeTranslateDescribeCommand
        }

        if sub_commands is not None:
            sub_command_parsers = {}
            sub_parsers = parser.add_subparsers(dest='transcribe_translate_command')

            for sub_command_name, sub_command_handler in sub_commands.items():
                sub_command_parser = sub_command_handler.init_parser(sub_parsers, command_name=sub_command_name)
                sub_command_parser.required = True
                sub_command_parsers[sub_command_name] = sub_command_parser

        return parser


class StateMachine:
    """Encapsulates Step Functions state machine actions."""

    def __init__(self, stepfunctions_client=None, state_machine_arn=None):
        """
        :param stepfunctions_client: A Boto3 Step Functions client.
        """
        if stepfunctions_client is None:
            stepfunctions_client = boto3.client('stepfunctions')

        self.stepfunctions_client = stepfunctions_client
        self.state_machine_arn = state_machine_arn

    def start(self, run_input, state_machine_arn=None):
        """
        Start a run of a state machine with a specified input. A run is also known
        as an "execution" in Step Functions.

        :param state_machine_arn: The ARN of the state machine to run.
        :param run_input: The input to the state machine, in JSON format.
        :return: The ARN of the run. This can be used to get information about the run,
                 including its current status and final output.
        """

        if state_machine_arn is None:
            state_machine_arn = self.state_machine_arn

        try:
            response = self.stepfunctions_client.start_execution(
                stateMachineArn=state_machine_arn, input=run_input
            )
        except ClientError as err:
            logger.error(
                "Couldn't start state machine %s. Here's why: %s: %s",
                state_machine_arn,
                err.response["Error"]["Code"],
                err.response["Error"]["Message"],
            )
            raise
        else:
            return response["executionArn"]


class StateMachineExecution:

    def __init__(self, stepfunctions_client=None, execution_arn=None):
        if stepfunctions_client is None:
            stepfunctions_client = boto3.client('stepfunctions')

        self.stepfunctions_client = stepfunctions_client
        self.execution_arn = execution_arn

    def describe(self):
        try:
            response = self.stepfunctions_client.describe_execution(
                executionArn=self.execution_arn
            )
        except ClientError as err:
            logger.error(
                "Couldn't describe state machine execution %s. %s: %s",
                self.execution_arn,
                err.response["Error"]["Code"],
                err.response["Error"]["Message"],
            )
            raise
        else:
            return response


def build_translate_input_for_file_and_language(input_data_config_s3_uri,
                                                source_language_code,
                                                target_languages,
                                                data_access_role_arn,
                                                output_s3_uri,
                                                client_token=None,
                                                source_file_content_type='text/plain'):
    if client_token is None:
        client_token = str(uuid.uuid4())

    translate_input = {
        "ClientToken": client_token,
        "DataAccessRoleArn": data_access_role_arn,
        "InputDataConfig": {
            "ContentType": source_file_content_type,
            "S3Uri": input_data_config_s3_uri
        },
        # "JobName": job_name,
        "OutputDataConfig": {
            "S3Uri": output_s3_uri
        },
        "SourceLanguageCode": source_language_code,
        "TargetLanguageCodes": target_languages
    }
    return translate_input


def get_default_output_s3_uri_from_opts(opts):
    output_bucket_name = getattr(opts, 'output_bucket_name', None)
    default_output_s3_uri = getattr(opts, 'output_s3_uri')
    if default_output_s3_uri is None and output_bucket_name is not None:
        default_output_s3_uri = f"s3://{output_bucket_name}"

    return default_output_s3_uri


def get_uri_from_opts(opts, attribute_name):
    output_s3_uri = getattr(opts, attribute_name, get_default_output_s3_uri_from_opts(opts))
    if output_s3_uri is None:
        # just in case the attribute was set to None in the options
        output_s3_uri = get_default_output_s3_uri_from_opts(opts)

    return output_s3_uri


def build_default_transcription_job_name(opts, media_file_uri=None, file_name_without_extension=None):
    if file_name_without_extension is None:
        if media_file_uri is None:
            media_file_uri = opts.media_file_uri
        file_name = os.path.basename(media_file_uri)
        file_name_without_extension, _file_name_ext = os.path.splitext(file_name)

    source_language_code = getattr(opts, 'transcription_source_language_code',
                                   DEFAULT_TRANSCRIPTION_SOURCE_LANGUAGE_CODE)
    source_language_for_file_name = source_language_code or 'auto'
    transcription_job_name = f"{file_name_without_extension}-{source_language_for_file_name}"

    return transcription_job_name


def determine_transcription_job_name(opts, media_file_uri=None, file_name_without_extension=None):
    transcription_job_name = getattr(opts, 'transcription_job_name', None)
    if transcription_job_name is None and getattr(opts, 'create_default_transcription_job_name',
                                                  DEFAULT_TRANSCRIPTION_CREATE_DEFAULT_JOB_NAME):
        transcription_job_name = build_default_transcription_job_name(opts, media_file_uri, file_name_without_extension)

    transcription_job_name = re.sub(r'[^0-9a-zA-Z._-]', '-', transcription_job_name)
    return transcription_job_name


def build_aws_transcribe_output_file_s3_uri(bucket_name, object_key, transcription_job_name=None, file_ext='.json'):
    """
    Build the output s3 URI the way AWS Transcribe would.

    More information about the output S3 URI is available in the AWS Transcribe StartTranscriptionJob API documentation:
    # noqa: E501
    `OutputBucketName <https://docs.aws.amazon.com/transcribe/latest/APIReference/API_StartTranscriptionJob.html#transcribe-StartTranscriptionJob-request-OutputBucketName>`_
    `OutputKey <https://docs.aws.amazon.com/transcribe/latest/APIReference/API_StartTranscriptionJob.html#transcribe-StartTranscriptionJob-request-OutputKey>`_

    Args:
        bucket_name (str): The name of the S3 bucket.
        object_key (str): The key of the S3 object.
        transcription_job_name (str, optional): The name of the Transcribe job. Defaults to None.
        file_ext (str, optional): The extension of the output file. Defaults to '.json'.

    Returns:
        str: The AWS Transcribe output file S3 URI.
    """
    output_s3_uri = os.path.join(f"s3://{bucket_name}", object_key)

    if not object_key.endswith(file_ext):
        if transcription_job_name is not None:
            output_s3_uri = os.path.join(output_s3_uri, transcription_job_name)

        output_s3_uri += file_ext

    return output_s3_uri


def build_transcription_output_uri_with_file_name(opts,
                                                  transcription_job_name=None,
                                                  file_name_without_extension=None):
    transcription_output_s3_uri = build_transcription_output_uri_without_folder_name(opts, transcription_job_name)
    if transcription_output_s3_uri is None:
        raise ValueError("Transcription output s3 URI must be specified.")

    transcription_output_folder_name = getattr(opts, 'transcription_output_folder_name',
                                               DEFAULT_TRANSCRIPTION_OUTPUT_FOLDER_NAME)

    if transcription_output_folder_name:
        transcription_output_s3_uri += f"{transcription_output_folder_name}/"

    # if we don't add the file name with the .json extension AWS Transcribe will treat it as a directory
    # and add job name followed by the .json extension as the file name.
    transcription_output_s3_uri += f"{file_name_without_extension}.json"

    return transcription_output_s3_uri


def build_transcription_output_uri_without_folder_name(opts, transcription_job_name=None):
    transcription_output_s3_uri = get_uri_from_opts(opts, 'transcription_output_s3_uri')
    if transcription_output_s3_uri is None:
        return None

    if not transcription_output_s3_uri.endswith('/'):
        transcription_output_s3_uri += '/'

    should_append_transcription_job_to_object_key = getattr(opts, 'append_transcription_job_to_object_key', True)
    if should_append_transcription_job_to_object_key:
        if transcription_job_name is None:
            transcription_job_name = determine_transcription_job_name(opts)
        if transcription_job_name is not None:
            transcription_output_s3_uri += f"{transcription_job_name}/"

    return transcription_output_s3_uri


def build_translate_output_s3_uri(opts, transcribe_output_s3_uri):
    translate_output_s3_uri = get_uri_from_opts(opts, 'translation_output_s3_uri')

    if transcribe_output_s3_uri.startswith(translate_output_s3_uri):
        translate_output_s3_uri = build_transcription_output_uri_without_folder_name(opts)

    if not translate_output_s3_uri.endswith('/'):
        translate_output_s3_uri += '/'

    translation_output_folder_name = getattr(opts, 'translation_output_folder_name',
                                             DEFAULT_TRANSLATION_OUTPUT_FOLDER_NAME)
    if translation_output_folder_name:
        translate_output_s3_uri += f'{translation_output_folder_name}/'

    return translate_output_s3_uri


def build_transcribe_output_s3_uri_from_transcribe_input(transcribe_input):
    transcribe_bucket_name = transcribe_input['OutputBucketName']
    transcribe_object_key = transcribe_input['OutputKey']
    transcribe_job_name = transcribe_input['TranscriptionJobName']
    transcribe_output_s3_uri = build_aws_transcribe_output_file_s3_uri(transcribe_bucket_name,
                                                                       transcribe_object_key,
                                                                       transcribe_job_name)
    return transcribe_output_s3_uri


def build_translate_input(opts, transcribe_output_s3_uri):
    """
    Build the AWS Translate input from the AWS Transcribe input.

    :param transcribe_output_s3_uri: The transcribe output s3 URI.
    :param opts: The command line options.
    :return: The AWS Translate input.
    """

    source_language_code = getattr(opts, 'translation_source_language_code',
                                   DEFAULT_TRANSLATION_SOURCE_LANGUAGE_CODE)

    translation_language_codes = getattr(opts, 'translation_language_codes', [])
    if len(translation_language_codes) == 1 and translation_language_codes[0] == 'all':
        translate_language_codes = get_translation_language_codes([source_language_code])
    else:
        translate_language_codes = translation_language_codes

    data_access_role_arn = getattr(opts, 'translation_data_access_role_arn', None)

    translate_output_s3_uri = build_translate_output_s3_uri(opts, transcribe_output_s3_uri)

    # We need the URI without a filename because AWS Transcribe requires a directory for the input
    translate_input_s3_uri = os.path.dirname(transcribe_output_s3_uri)  # .replace('.json', f".{subtitle_format}")
    if not translate_input_s3_uri.endswith('/'):
        translate_input_s3_uri += '/'

    translate_inputs = []
    for language_code in translate_language_codes:
        target_languages = [language_code]
        translate_input = build_translate_input_for_file_and_language(
            input_data_config_s3_uri=translate_input_s3_uri,
            source_language_code=source_language_code,
            target_languages=target_languages,
            data_access_role_arn=data_access_role_arn,
            output_s3_uri=translate_output_s3_uri
        )
        if translate_input is not None:
            translate_inputs.append(translate_input)

    translate_input = {
        "Inputs": translate_inputs
    }

    return translate_input


def parse_s3_uri(uri):
    parsed_uri = urlparse(uri)
    if not parsed_uri.netloc:
        raise ValueError("Bad s3 uri. Please provide uri in format: s3://bucket_name/object_key")
    bucket_name = parsed_uri.netloc
    object_key = parsed_uri.path.lstrip('/')
    return bucket_name, object_key


def build_transcribe_input(opts):
    media_file_uri = opts.media_file_uri
    file_name = os.path.basename(media_file_uri)
    file_name_without_extension, _file_name_ext = os.path.splitext(file_name)

    source_language_code = getattr(opts, 'transcription_source_language_code',
                                   DEFAULT_TRANSCRIPTION_SOURCE_LANGUAGE_CODE)

    subtitle_formats = getattr(opts, 'subtitle_formats', DEFAULT_TRANSCRIPTION_SUBTITLE_FORMATS)

    should_identify_language = getattr(opts, 'auto_identify_source_language',
                                       DEFAULT_TRANSCRIPTION_AUTO_IDENTIFY_SOURCE_LANGUAGE)

    if should_identify_language:
        source_language_code = None

    transcription_job_name = determine_transcription_job_name(opts, file_name_without_extension)

    transcription_output_s3_uri = build_transcription_output_uri_with_file_name(
        opts,
        transcription_job_name=transcription_job_name,
        file_name_without_extension=file_name_without_extension)

    output_bucket_name, output_object_key = parse_s3_uri(transcription_output_s3_uri)

    transcribe_input = {
        "Media": {
            "MediaFileUri": media_file_uri
        },
        "IdentifyLanguage": should_identify_language,
        "LanguageCode": source_language_code,
        "OutputBucketName": output_bucket_name,
        "OutputKey": output_object_key,
        "TranscriptionJobName": transcription_job_name,
        "Subtitles": {
            "Formats": subtitle_formats,
            "OutputStartIndex": 1
        }
    }

    return transcribe_input


def build_run_input(opts):
    """
    Build the input to the state machine.

    @see https://docs.aws.amazon.com/transcribe/latest/APIReference/API_StartTranscriptionJob.html

    :param opts: Input options.
    :return: The input to the state machine, in JSON format.
    """

    transcribe_input = build_transcribe_input(opts)
    transcribe_output_s3_uri = build_transcribe_output_s3_uri_from_transcribe_input(transcribe_input)

    translate_input = build_translate_input(opts, transcribe_output_s3_uri)

    sf_input = {
        "Transcribe": transcribe_input,
        "Translate": translate_input
    }
    return sf_input


def run_step_function(state_machine_arn, run_input):
    logger.debug('Running state machine: %s %s', state_machine_arn, run_input)
    run_input_json: str = json.dumps(run_input)
    execution_arn = StateMachine(state_machine_arn=state_machine_arn).start(run_input_json)
    return execution_arn


def get_translation_language_codes(filter_values=None):
    if filter_values is None:
        filter_values = []
    filter_values.append('auto')

    client = boto3.client('translate')
    response = client.list_languages(MaxResults=500)
    return [language['LanguageCode']
            for language in response['Languages'] if language['LanguageCode'] not in filter_values]


def parse_command_line(cli_args, env_vars, sub_commands=None):
    parser = argparse.ArgumentParser(
        description='Envoi Transcribe and Translate Command Line Utility',
    )

    parser.add_argument("--log-level", dest="log_level",
                        default="WARNING",
                        help="Set the logging level (options: DEBUG, INFO, WARNING, ERROR, CRITICAL)")

    if sub_commands is not None:
        sub_command_parsers = {}
        sub_parsers = parser.add_subparsers(dest='command')
        sub_parsers.required = True

        for sub_command_name, sub_command_handler in sub_commands.items():
            sub_command_parser = sub_command_handler.init_parser(sub_parsers, command_name=sub_command_name)
            sub_command_parser.required = True
            sub_command_parsers[sub_command_name] = sub_command_parser

    (opts, args) = parser.parse_known_args(cli_args)
    return opts, args, env_vars, parser


def lambda_handler(event, _context):
    print("Received event: " + json.dumps(event, indent=2))

    event_record = event['Records'][0]

    event_source = event_record['eventSource']
    match event_source:
        case 'aws:s3':
            handle_s3_event_record(event_record)
        case _:
            raise NotImplementedError(f"Unsupported event source: {event_source}")

    return {"success": True}


def handle_s3_event_record(event_record):
    """
    :param event_record: The event object containing information about the S3 event.
    :return: Object

    This method handles an S3 event triggered by a new file upload to the S3 bucket. It extracts relevant information
    from the event and a configuration file, and then calls the appropriate command handler.
    """

    event_name = event_record['eventName']
    if event_name != 'ObjectCreated:Put':
        raise NotImplementedError(f"Unsupported S3 event: {event_name}")

    config_file_uri = os.environ.get('CONFIG_FILE_URI')
    if config_file_uri is None:
        raise ValueError("CONFIG_FILE_URI environment variable must be set.")

    config = StorageHelper.read_file_json(config_file_uri)
    if config is None:
        raise ValueError(f"Error loading config from {config_file_uri}")

    data_from_s3 = event_record['s3']

    s3_bucket = data_from_s3['bucket']
    s3_object = data_from_s3['object']

    media_file_uri = f"s3://{s3_bucket['name']}/{s3_object['key']}"
    config_input = config['input']
    config_input['media_file_uri'] = media_file_uri
    opts = SimpleNamespace(**config_input)

    command_handler = EnvoiTranscribeTranslateCreateCommand(opts)
    command_handler.run()

    return {"success": True}


def handle_cli_execution():
    """
    Handles the execution of the command-line interface (CLI) for the application.

    :returns: Returns 0 if successful, 1 otherwise.
    """
    cli_args = sys.argv[1:]
    env_vars = os.environ.copy()

    sub_commands = {
        'create': EnvoiTranscribeTranslateCreateCommand,
        'describe': EnvoiTranscribeTranslateDescribeCommand,
        # 'transcribe-translate': EnvoiTranscribeTranslateCommand,
    }

    opts, _unhandled_args, env_vars, parser = parse_command_line(cli_args, env_vars, sub_commands)

    # We create a new handler for the root logger, so that we can get
    # setLevel to set the desired log level.
    ch = logging.StreamHandler()
    ch.setLevel(opts.log_level.upper())
    logger.addHandler(ch)

    try:
        # If 'handler' is in args, run the correct handler
        if hasattr(opts, 'handler'):
            command_handler = opts.handler(opts)
            command_handler.run()
        else:
            parser.print_help()
            return 1

        return 0
    except Exception as e:
        logger.exception(e)
        return 1


if __name__ == '__main__':
    EXIT_CODE = handle_cli_execution()
    sys.exit(EXIT_CODE)
