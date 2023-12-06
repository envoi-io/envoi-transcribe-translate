#!/usr/bin/env python3

import argparse
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
import json
from json import JSONEncoder
import logging
import os
import sys
from urllib.parse import urlparse
import uuid

logger = logging.Logger('envoi-transcribe-translate')


class CustomJsonEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return JSONEncoder.default(self, obj)


class S3Helper:

    def __init__(self, client=None):
        self.s3 = client or boto3.client('s3')

    def read_object(self, bucket, key):
        try:
            response = self.s3.get_object(Bucket=bucket, Key=key)
            return response['Body'].read().decode('utf-8')
        except ClientError as e:
            if e.response['Error']['Code'] == "404":
                return None
            else:
                raise e

    def read_object_json(self, bucket, key):
        file_contents = self.read_object(bucket, key)
        return json.loads(file_contents) if file_contents is not None else None


# class Options:
#
#     def __init__(self, config_path):
#         self.config_path = config_path
#         self.config = self.load_config() if config_path else {}
#         self.overrides = {}
#
#     def load_config(self):
#         with open(self.config_path) as config_file:
#             opts = json.load(config_file)  # Assumes your config file is in json format
#             self.config = opts
#
#     def load_args(self, parser=None):
#         if parser is None:
#             opts = {}
#         else:
#             (opts, args) = parser.parse_known_args()
#
#         self.overrides = opts
#         return opts
#
#     def get(self, key, default=None):
#         # First, try to get the value from command line arguments
#         value = getattr(self.overrides, key, None)
#         # If not supplied, try the config file
#         if value is None:
#             value = self.config.get(key, None)
#         # If still not found, return the default
#         return value if value is not None else default


class EnvoiTranscribeTranslateCreateCommand:

    def __init__(self, opts):
        self.opts = opts

    def run(self, opts=None):
        if opts is None:
            opts = self.opts

        run_input = build_run_input(opts)
        if opts.dry_run:
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
        # parser.add_argument('--auto-identify-source-language', dest='auto_identify_source_language',
        #                     action='store_true',
        #                     help='Tells transcribe to try and automatically identify the source language of the '
        #                          'media file.'
        parser.add_argument('--state-machine-arn', dest='state_machine_arn',
                            help='The ARN of the state machine to run.')
        parser.add_argument('--source-language', dest='source_language_code',
                            default='en',
                            help='The language of the source file.')
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
        parser.add_argument('--transcription-job-name', dest='transcription_job_name',
                            default=None,
                            help='The name of the job.')
        parser.add_argument('--transcription-output-s3-uri', dest='transcription_output_s3_uri',
                            default=None,
                            help='The S3 URI of the translate output file location.')
        parser.add_argument('--translation-data-access-role-arn', dest='translation_data_access_role_arn',
                            default=None,
                            help='The ARN of the role to use for translate to access data.')
        parser.add_argument('-l', '--translation-languages', dest='translation_languages',
                            nargs="+",
                            help='The languages to translate to.')
        parser.add_argument('--translation-output-s3-uri', dest='translation_output_s3_uri',
                            default=None,
                            help='The S3 URI of the translate output file location.')

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
        logger.debug(f"Description: {description}")

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
                                                job_name="",
                                                source_file_content_type='text/plain',
                                                opts=None):
    if opts is None:
        opts = {}

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


def get_uri_from_opts(opts, attribute_name):
    output_bucket_name = getattr(opts, 'output_bucket_name', None)
    default_output_s3_uri = getattr(opts, 'output_s3_uri')
    if default_output_s3_uri is None and output_bucket_name is not None:
        default_output_s3_uri = f"s3://{output_bucket_name}"

    output_s3_uri = (getattr(opts, attribute_name, default_output_s3_uri)
                                   or default_output_s3_uri)

    return output_s3_uri


def build_translate_input_from_transcribe_input(transcribe_input, opts):
    """
    Build the AWS Translate input from the transcribe input.

    :param transcribe_input: The transcribe input.
    :param opts: The command line options.
    :return: The AWS Translate input.
    """

    transcribe_bucket_name = transcribe_input['OutputBucketName']
    transcribe_object_key = transcribe_input['OutputKey']
    base_output_s3_uri = f"s3://{transcribe_bucket_name}/{transcribe_object_key}"

    source_language_code = getattr(transcribe_input, 'SourceLanguageCode', None)
    subtitles = transcribe_input['Subtitles']
    subtitle_formats = subtitles['Formats']

    translation_languages = getattr(opts, 'translation_languages', [])
    if len(translation_languages) == 1 and translation_languages[0] == 'all':
        translate_language_codes = get_translation_languages([source_language_code])
    else:
        translate_language_codes = translation_languages

    data_access_role_arn = getattr(opts, 'translation_data_access_role_arn')

    translate_output_s3_uri = get_uri_from_opts(opts, 'translation_output_s3_uri')

    translate_inputs = []
    for subtitle_format in subtitle_formats:
        output_s3_uri = f"${base_output_s3_uri}.{subtitle_format}"
        for language_code in translate_language_codes:
            target_languages = [language_code]
            translate_input = build_translate_input_for_file_and_language(
                input_data_config_s3_uri=output_s3_uri,
                source_language_code=source_language_code,
                target_languages=target_languages,
                data_access_role_arn=data_access_role_arn,
                output_s3_uri=translate_output_s3_uri,
                opts=opts
            )
            if translate_input is not None:
                translate_inputs.append(translate_input)

    translate_input = {
        "Translate": {
            "Inputs": translate_inputs
        }
    }

    return translate_input


def parse_s3_uri(uri):
    parsed_uri = urlparse(uri)
    if not parsed_uri.netloc:
        raise ValueError("Bad s3 uri. Please provide uri in format: s3://bucket_name/object_key")
    bucket_name = parsed_uri.netloc
    object_key = parsed_uri.path[1:]  # exclude the leading '/'
    return bucket_name, object_key


def build_transcribe_input(opts):
    media_file_uri = opts.media_file_uri
    parsed_uri = urlparse(media_file_uri)
    file_name = os.path.basename(parsed_uri.path)
    file_name_without_extension, file_name_ext = os.path.splitext(file_name)

    transcription_job_name = opts.transcription_job_name or f"{file_name_without_extension}-{str(uuid.uuid4())[:8]}"

    source_language_code = getattr(opts, 'source_language_code', 'en')
    subtitle_formats = getattr(opts, 'subtitle_formats', ['srt', 'vtt'])

    # translation_languages = build_translate_inputs(
    #     source_langauge_code=source_langauge_code,
    #     # input_s3_uris=opts.,
    #     translation_languages=opts.translation_languages,
    #     output_bucket_name=opts.output_bucket_name
    # )

    if hasattr(opts, 'auto_identify_source_language'):
        should_identify_language = opts['auto_identify_source_language']
    else:
        should_identify_language = False

    transcription_output_s3_uri = get_uri_from_opts(opts, 'transcription_output_s3_uri')
    if transcription_output_s3_uri is None:
        raise ValueError(f"Transcription output s3 URI must be specified.")

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

    :param opts: The command line options.
    :return: The input to the state machine, in JSON format.
    """

    transcribe_input = build_transcribe_input(opts)
    translate_input = build_translate_input_from_transcribe_input(transcribe_input, opts)

    sf_input = {
        "Transcribe": transcribe_input,
        "Translate": translate_input
    }
    return sf_input


def run_step_function(state_machine_arn, run_input):
    logger.debug(f"Running state machine: {state_machine_arn} {run_input}")
    run_input_json: str = json.dumps(run_input)
    execution_arn = StateMachine(state_machine_arn=state_machine_arn).start(run_input_json)
    return execution_arn


# def build_translate_inputs(source_langauge_code,
#                            translation_languages,
#                            output_bucket_name,
#                            source_file_uri=None,
#                            source_file_content_type=None,
#                            output_s3_uri=None):
#     logger.debug("Processing translation languages: %s", translation_languages)
#     if not translation_languages:
#         return []
#
#     translate_data_access_role_arn = ""
#
#     if len(translation_languages) == 1 and translation_languages[0] == 'all':
#         translation_languages = get_translation_languages([source_langauge_code])
#
#     return [process_transcription_language(source_langauge_code,
#                                            target_language,
#                                            translate_data_access_role_arn,
#                                            source_file_uri,
#                                            output_s3_uri)
#             for target_language in translation_languages]
#
#
# def process_transcription_language(source_language_code,
#                                    target_languages,
#                                    data_access_role_arn,
#                                    source_file_uri,
#                                    output_s3_uri):
#     source_file_content_type = 'text/plain'
#     # {
#     #     "LanguageCode": language_code,
#     #     "OutputBucketName": output_bucket_name,
#     # }
#     return {
#         "ClientToken": str(uuid.uuid4()),
#         "DataAccessRoleArn": data_access_role_arn,
#         "InputDataConfig": {
#             "ContentType": source_file_content_type,
#             "S3Uri": source_file_uri
#         },
#         "JobName": "string",
#         "OutputDataConfig": {
#             "S3Uri": output_s3_uri
#         },
#         "SourceLanguageCode": source_language_code,
#         "TargetLanguageCodes": target_languages
#     }


def get_translation_languages(filter_values=None):
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


def lambda_handler(event, context):
    print("Received event: " + json.dumps(event, indent=2))
    try:
        print("Context: " + json.dumps(context, indent=2))
    except Exception as e:
        print("Exception print context.", e)

    event_record = event['Records'][0]

    event_source = event_record['eventSource']
    match event_source:
        case 'aws:s3':
            handle_s3_event_record(event_record)
        case _:
            raise Exception(f"Unsupported event source: {event_source}")

    return context


def handle_s3_event_record(event_record):
    """
    :param event_record: The event object containing information about the S3 event.
    :return: Object

    This method handles an S3 event triggered by a new file upload to the S3 bucket. It extracts relevant information
    from the event and a configuration file, and then calls the appropriate command handler.
    """

    event_name = event_record['eventName']

    config_file_path = os.environ.get('CONFIG_FILE_PATH')
    if config_file_path is not None:
        with open(config_file_path) as config_file:
            config = json.load(config_file)

    data_from_s3 = event_record['s3']

    s3_bucket = data_from_s3['bucket']
    s3_object = data_from_s3['object']

    media_file_uri = f"s3://{s3_bucket.name}/{s3_object.key}"
    opts = {
        'media_file_uri': media_file_uri,
    }
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

    opts, args, env_vars, parser = parse_command_line(cli_args, env_vars, sub_commands)

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
    exit_code = handle_cli_execution()
    sys.exit(exit_code)
