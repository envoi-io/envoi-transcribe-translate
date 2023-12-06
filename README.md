# Envoi Transcribe Translate

Envoi Transcribe Translate allows for files to be transcribed and translated using AWS services.

## Overview

A utility that submits media files to an AWS Step Functions to process transcription jobs using AWS Transcription.



## Deployment


### Install AWSCLI using Homebrew
brew install python

brew install awscli



### Backend

To set up the required AWS resources run the [initialization script](deploy/install-transcribe-translate.sh)

By default, this will create a IAM role, IAM policy, and a step function.


## Usage

### Create

```
usage: envoi-transcribe-translate.py create [-h] --media-file-uri MEDIA_FILE_URI [--state-machine-arn STATE_MACHINE_ARN] [--source-language SOURCE_LANGUAGE_CODE] [--log-level LOG_LEVEL] [--dry-run] [--output-bucket-name OUTPUT_BUCKET_NAME] [--output-s3-uri OUTPUT_S3_URI] [--transcription-job-name TRANSCRIPTION_JOB_NAME] [--transcription-output-s3-uri TRANSCRIPTION_OUTPUT_S3_URI] [--translation-data-access-role-arn TRANSCRIPTION_DATA_ACCESS_ROLE_ARN]
                                            [-l TRANSLATION_LANGUAGES [TRANSLATION_LANGUAGES ...]] [--translation-output-s3-uri TRANSLATION_OUTPUT_S3_URI]

options:
  -h, --help            show this help message and exit
  --media-file-uri MEDIA_FILE_URI
                        The S3 URI of the media file to transcribe.
  --state-machine-arn STATE_MACHINE_ARN
                        The ARN of the state machine to run.
  --source-language SOURCE_LANGUAGE_CODE
                        The language of the source file.
  --log-level LOG_LEVEL
                        Set the logging level (options: DEBUG, INFO, WARNING, ERROR, CRITICAL)
  --dry-run             Do not run the state machine, just print the input.
  --output-bucket-name OUTPUT_BUCKET_NAME
                        A default bucket for file output. This will be used if a more specific S3 URI is not supplied. ex: --output-s3-uri, --transcription-output-s3-uri, --translation-output-s3-uri
  --output-s3-uri OUTPUT_S3_URI
                        A default S3 URI for file output. This will be used if a more specific S3 URI is not supplied. ex: --transcription-output-s3-uri, --translation-output-s3-uri
  --transcription-job-name TRANSCRIPTION_JOB_NAME
                        The name of the job.
  --transcription-output-s3-uri TRANSCRIPTION_OUTPUT_S3_URI
                        The S3 URI of the translate output file location.
  --translation-data-access-role-arn TRANSCRIPTION_DATA_ACCESS_ROLE_ARN
                        The ARN of the role to use for translate to access data.
  -l TRANSLATION_LANGUAGES [TRANSLATION_LANGUAGES ...], --translation-languages TRANSLATION_LANGUAGES [TRANSLATION_LANGUAGES ...]
                        The languages to translate to.
  --translation-output-s3-uri TRANSLATION_OUTPUT_S3_URI
                        The S3 URI of the translate output file location.

```

### Describe

```
usage: envoi-transcribe-translate.py describe [-h] [--execution-arn EXECUTION_ARN] [--uris-only]

options:
  -h, --help            show this help message and exit
  --execution-arn EXECUTION_ARN
                        The ARN of the state machine execution to describe.
  --uris-only           Only print the URIs of the output files.

```
