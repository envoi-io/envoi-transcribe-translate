# Envoi Transcribe Translate

Envoi Transcribe Translate allows for files to be transcribed and translated using AWS services.

## Overview

A utility that submits media files to an AWS Step Functions to process transcription jobs using AWS Transcription.

## Deploy Required AWS Resources

### Prerequisites

[AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)

> You can also use homebrew to install the AWS CLI by running `brew install awscli`

[jq](https://jqlang.github.io/jq/)

> You can also use homebrew to install the jq utility by running `brew install jq`

### Installation Script

To set up the required AWS resources run the [initialization script](deploy/install-transcribe-translate.sh)

By default, this will create a IAM role, IAM policy, and a step function.

## CLI Usage

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

## Running Envoi Transcribe Translate as a Lambda Function

You can deploy the script as a Lambda function and have it handle S3 object creation events.

### Using the console

- ***Open the AWS console***
- ***Create the Lambda Execution IAM Role***

1. Navigate to the [IAM service dashboard](https://us-east-1.console.aws.amazon.com/iam/home)
2. Select `Roles` from the navigation menu
3. Click the `Create Role` button
4. Enter `Lambda` into the `Service or use case` field
5. Click the `Add` button
6. Click the `Next` button
7. In the `Role name` field, enter the name you would like to give the role
   > Example: envoi-transcribe-translate-lambda-execution-role
8. Click the `Create role` button
9. Find and click the role name of the role you just created
10. Click `Add permissions`
11. Select `Create inline policy`
12. Enter  `Step Functions` into the `Choose a service` field
13. Enter `StartExecution` into the `Specify actions from the service to be allowed` field 
14. In the `Resources` section click `Add ARNs to restrict access.`
15. Select `This account`
16. Enter the region where the Envoi Transcribe Transcript Step Function is loaded
17. In the `Resource state machine name` enter the name of the Envoi Transcribe Translate step function
18. Click the `Add ARNs` button
19. **OPTIONAL** If you plan on using S3 to store the configuration file for the Lambda function then you will need to give access to the bucket. If not then you can skip to step 12.
          
     1. Click the `Add more permissions` button
     2. Enter `S3` into the `Chooose a service` field
     3. In `Actions allowed` you will need both `ListBucket` and `GetObject`
     4. Click `Add ARNs`
   
20. Enter the name of the bucket into the field under the `Any bucket name` checkbox
21. Click the `Add ARNs` button
22. Click the `Next` button
23. Enter a name for your policy
24. Click the `Create policy` button
  
- ***Create the Lambda Function***

1. Navigate to the [Lambda service dashboard](https://us-east-1.console.aws.amazon.com/lambda/home)
2. Click the `Create function` button
3. Enter a name for your function
   > Example: envoi-transcribe-translate
4. In the `Runtime` field you should select a python runtime >= `Python 3.11`
5. Expand the `Change default execution role` section
6. Click `Use an existing role`
7. Enter the name of the execution role you created before
8. Click the `Create function` button
9. Copy and paste the contents of the `envoi_transcribe_translate.py` into the `Code source` section

- ***Add the Trigger to the Lambda Function***
1. Click the `Configuration` tab
2. Select the `Triggers` tab on the left sidebar
3. Click the `Add trigger` button
4. Enter `s3` into the `Select a source` field
5. Enter the name of the bucket that will trigger the lambda into the `Bucket` field
6. Leave `All object create events` select for the `Event types` field
7. Enter any prefix that should apply for the trigger
8. Click the `Recursive Invocation` checkbox
9. Click the `Add` button

- ***Add the Configuration File to S3***
1. Navigate to the [S3 dashboard](https://s3.console.aws.amazon.com/s3/home)
2. Create or select a bucket that you will use to store the configuration file 
3. Upload a configuration file to a bucket and path of your choosing.
   - Example:
   ```json
   {
     "input": {
       "state_machine_arn": "arn:aws:states:us-east-1:{ADD AWS ACCOUNT ID}:stateMachine:envoi-transcribe-translate",
       "output_s3_uri": "s3://envoi-transcribe-translate/jobs",
       "translation_data_access_role_arn": "arn:aws:iam::{ADD AWS ACCOUNT ID}:role/envoi-translate",
       "translation_language_codes": [
         "es"
       ]
     }
   }
   ```
5. Click on the file in the S3
6. Copy the `S3 URI` to your clipboard

- ***Add the CONFIG_FILE_URI to the Lambda Environment Variables Configuration***
1. Navigate to the `Lambda` service [dashboard](https://us-east-1.console.aws.amazon.com/lambda/home)
2. Find and click on the Lambda function created earlier
3. Click on the `Configuration` tab
4. Click on the `Enviornment variables` tab in the left hand list of tabs
5. Click the `Edit` button
6. Click the `Add environment varible` button
7. Enter `CONFIG_FILE_URI` into the `Key` field
8. Enter the `S3 URI` into the `Value` field.
9. Click the `Save` button

#### Using the CLI

1. Populate these environment variables
    ```shell
    export AWS_ACCOUNT_ID=
    export LAMBDA_FUNCTION_NAME=
    export LAMBDA_ROLE_NAME=
    export LAMBDA_TRIGGER_S3_BUCKET_NAME=
    export LAMBDA_FUNCTION_CONFIG_FILE_URI=
    ```
2. Create the IAM role
    ```shell
      ROLE_NAME=envoi-transcribe-translate-role
      aws iam create-role \
      --path "/service-role/" \
      --role-name "${LAMBDA_ROLE_NAME}" \
      --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [
            {
              "Effect": "Allow",
              "Principal": {
                "Service": "lambda.amazonaws.com"
              },
              "Action": "sts:AssumeRole"
            }
          ]
        }' 
    ```
3. Add the policy to the Role 
   ```shell
     aws iam put-role-policy \
     --role-name "${LAMBDA_ROLE_NAME}" \
     --policy-name "${LAMBDA_ROLE_POLICY}" \
     --policy-document '{
       "Version": "2012-10-17",
       "Statement": [
           {
               "Sid": "VisualEditor0",
               "Effect": "Allow",
               "Action": [
                   "states:StartExecution",
                   "states:UntagResource",
                   "states:TagResource"
               ],
               "Resource": [
                   "arn:aws:states:*:${AWS_ACCOUNT_ID}:stateMachine:*"
               ]
           },
           {
               "Sid": "EnvoiTranslateTranscribeS3",
               "Effect": "Allow",
               "Action": [
                   "s3:GetObject",
                   "s3:ListBucket"
               ],
               "Resource": [
                   "arn:aws:s3:::*"
               ]
           }
       ]
   }'
   ```
4. Create the Lambda function
    ```shell
    aws lambda create-function \
    --function-name $LAMBDA_FUNCTION_NAME \
    --runtime python3.11 \
    --role ${LAMBDA_ROLE_ARN} \
    --handler envoi_translate_transcribe.lambda_handler \
    --environment "Variables={CONFIG_FILE_URI=${LAMBDA_FUNCTION_CONFIG_FILE_URI}"
    --code "Uri=fileb://./" 
    ```
5. Create the S3 trigger
    ```shell
    aws lambda add-permission \
        --function-name ${LAMBDA_FUNCTION_NAME} \
        --statement-id s3-trigger \
        --action lambda:InvokeFunction \
        --principal s3.amazonaws.com \
        --source-arn arn:aws:s3:::${LAMBDA_TRIGGER_S3_BUCKET_NAME}
   ```