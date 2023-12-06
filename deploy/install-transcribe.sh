#!/bin/bash

# Usage function
usage() {
  cat << EOF
Usage: $0 [--policy-arn ARN] [--policy-name Name] [--role-arn ARN] [--role-name Name] [--skip-role-policy-attachment] [--step-function-name Name]

Creates the Envoi Translate Transcribe step function and the required IAM resources

Options:
  --policy-arn ARN
    The ARN for the policy (default: ${POLICY_ARN:-"None"})
    If set then the policy name will be set from the ARN

  --policy-name NAME
    Policy name (default: derived from policy ARN or "${POLICY_NAME:-None}")

  --role-arn ARN
    The ARN for the role (default: ${ROLE_ARN:-"None"})
    If set then the role name will be set from the ARN

  --role-name NAME
    Role name (default: derived from role ARN or "${ROLE_NAME:-None}")

  --skip-role-policy-attachment
    Skips role policy attachment (default: false)

  --step-function-name NAME
    Step function name (default: "${STEP_FUNCTION_NAME:-None}")


Argument Types:
  ARN   AWS Resource Number.
  NAME  A string representing the name.

EOF
}

# Initialize the environment
STEP_FUNCTION_NAME=${STEP_FUNCTION_NAME:-envoi-transcribe-translate}
POLICY_NAME=${POLICY_NAME:-${STEP_FUNCTION_NAME}}
ROLE_NAME=${ROLE_NAME:-${STEP_FUNCTION_NAME}}

# You can specify the name of the step function by setting the STEP_FUNCTION_NAME environment variable
# The default value is envoi-transcribe-translate
# export STEP_FUNCTION_NAME=${STEP_FUNCTION_NAME:-"envoi-transcribe-translate"}

# You can specify an existing policy to use by setting the POLICY_ARN environment variable
# Leave the value blank to create a new policy
# export POLICY_ARN=

# You can specify an existing role to use by setting the ROLE_ARN environment variable
# Leave the value blank to create a new role
# export ROLE_ARN=

# You can specify the name of the step function's service role by setting the ROLE_NAME environment variable
# The default value is the name of the step function or the name of the existing role if ROLE_ARN is set
# export ROLE_NAME=${ROLE_NAME:-${STEP_FUNCTION_NAME}}


# You can specify the name of the step function's policy by setting the POLICY_NAME environment variable
# The default value is the name of the step function or the name of the existing policy if POLICY_ARN is set
# export POLICY_NAME=${POLICY_NAME:-${STEP_FUNCTION_NAME}}

skip_role_policy_attachment=false

# Parse command-line arguments
while (( "$#" )); do
  case "$1" in
    --policy-arn)
      if [ -n "$2" ] && [ "${2:0:1}" != "-" ]; then
        POLICY_ARN=$2
        shift 2
      else
        echo "Error: Argument for $1 is missing" >&2
        exit 1
      fi
      ;;
    --policy-name)
      if [ -n "$2" ] && [ "${2:0:1}" != "-" ]; then
        POLICY_NAME=$2
        shift 2
      else
        echo "Error: Argument for $1 is missing" >&2
        exit 1
      fi
      ;;
    --role-arn)
      if [ -n "$2" ] && [ "${2:0:1}" != "-" ]; then
        ROLE_ARN=$2
        shift 2
      else
        echo "Error: Argument for $1 is missing" >&2
        exit 1
      fi
      ;;
    --role-name)
      if [ -n "$2" ] && [ "${2:0:1}" != "-" ]; then
        ROLE_NAME=$2
        shift 2
      else
        echo "Error: Argument for $1 is missing" >&2
        exit 1
      fi
      ;;
      --skip-role-policy-attachment)
      skip_role_policy_attachment=true
      shift 1
      ;;
      --step-function-name)
      if [ -n "$2" ] && [ "${2:0:1}" != "-" ]; then
        STEP_FUNCTION_NAME=$2
        shift 2
      else
        echo "Error: Argument for $1 is missing" >&2
        exit 1
      fi
      ;;
      -h|--help)
        usage
        exit
      ;;
    *)
      # If unknown option, simply shift
      shift 1
      ;;
  esac
done

if [ -n "${ROLE_ARN}" ]; then
  IFS="/" read -r -a ROLE_ARN_SPLIT <<< "${ROLE_ARN}"
  ROLE_NAME=${ROLE_ARN_SPLIT[${#ROLE_ARN_SPLIT[@]}-1]}
else
  ROLE_NAME=${ROLE_NAME:-${STEP_FUNCTION_NAME}}
fi
export ROLE_NAME

if [ -n "${POLICY_ARN}" ]; then
  POLICY_ARN=${EXISTING_POLICY_ARN}
  IFS="/" read -r -a POLICY_ARN_SPLIT <<< "${EXISTING_POLICY_ARN}"
  POLICY_NAME=${POLICY_ARN_SPLIT[${#POLICY_ARN[@]}-1]}
else
  POLICY_NAME=${POLICY_NAME:-${STEP_FUNCTION_NAME}}
fi
export POLICY_NAME

ASSUME_ROLE_POLICY_JSON=$(cat <<-EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "states.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
)

POLICY_JSON=$(cat <<-EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "envoiTranscribe",
      "Effect": "Allow",
      "Action": [
        "transcribe:GetTranscriptionJob",
        "transcribe:StartTranscriptionJob",
        "transcribe:ListTagsForResource"
      ],
      "Resource": "*"
    },
    {
      "Sid": "envoiTranscribeS3",
      "Effect": "Allow",
      "Action": [
        "s3:ListTagsForResource",
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:PutObjectTagging"
      ],
      "Resource": "*"
    },
    {
      "Sid": "envoiTranslate",
      "Effect": "Allow",
      "Action": [
        "translate:CreateParallelData",
        "translate:DescribeTextTranslationJob",
        "translate:GetParallelData",
        "translate:ListTagsForResource",
        "translate:TagResource",
        "translate:TranslateText",
        "translate:UntagResource",
        "translate:UpdateParallelData"
      ],
      "Resource": "*"
    }
  ]
}
EOF
)

STEP_FUNCTION_JSON=$(cat <<-EOF
{
  "Comment": "A state machine that transcribes documents.",
  "StartAt": "StartTranscriptionJob",
  "States": {
    "StartTranscriptionJob": {
      "Type": "Task",
      "Parameters": {
        "Media.$": "$.Transcribe.Media",
        "IdentifyLanguage": "true",
        "OutputBucketName.$": "$.Transcribe.OutputBucketName",
        "TranscriptionJobName.$": "$.Transcribe.TranscriptionJobName",
        "Subtitles": {
          "Formats": [
            "srt",
            "vtt"
          ],
          "OutputStartIndex": 1
        }
      },
      "Resource": "arn:aws:states:::aws-sdk:transcribe:startTranscriptionJob",
      "Next": "GetTranscriptionJob"
    },
    "GetTranscriptionJob": {
      "Type": "Task",
      "Parameters": {
        "TranscriptionJobName.$": "$.TranscriptionJob.TranscriptionJobName"
      },
      "Resource": "arn:aws:states:::aws-sdk:transcribe:getTranscriptionJob",
      "Next": "Is Running?"
    },
    "Is Running?": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.TranscriptionJob.TranscriptionJobStatus",
          "StringEquals": "IN_PROGRESS",
          "Next": "Wait for Transcription to Complete"
        }
      ],
      "Default": "Success"
    },
    "Success": {
      "Type": "Succeed"
    },
    "Wait for Transcription to Complete": {
      "Type": "Wait",
      "Seconds": 5,
      "Next": "GetTranscriptionJob"
    }
  }
}
EOF
)

if [ -z "${ROLE_ARN}" ]; then
  [ -z "${ROLE_NAME}" ] && echo "ROLE_ARN or ROLE_NAME must be specified." && exit 1
  echo "Creating role named \"${ROLE_NAME}\"..."
  # Create the role
  if ! ROLE_RESPONSE=$(aws iam create-role --role-name "${ROLE_NAME}" --path /service-role/ --assume-role-policy-document "${ASSUME_ROLE_POLICY_JSON}" --max-session-duration 3600 --output json); then
      echo "Error: Failed to create the role ${ROLE_NAME}" >&2
      echo "${ROLE_RESPONSE}"
      exit 1
  fi
  echo "Role created successfully."

  # Get the ARN of the role using jq
  ROLE_ARN=$(echo "${ROLE_RESPONSE}" | jq -r '.Role.Arn')
fi
echo "Using role: \"${ROLE_ARN}\""

if [ -z "${POLICY_ARN}" ]; then
  [ -z "${POLICY_NAME}" ] && echo "POLICY_ARN or POLICY_NAME must be specified." && exit 1
  echo "Creating policy named \"${POLICY_NAME}\"..."
  # Create the policy and capture the output into an environment variable
  POLICY_RESPONSE=$(aws iam create-policy --policy-name "${POLICY_NAME}" --policy-document "${POLICY_JSON}" --output json)
  if ! POLICY_RESPONSE=$(aws iam create-policy --policy-name "${POLICY_NAME}" --policy-document "${POLICY_JSON}" --output json); then
      echo "Error: Failed to create the policy ${ROLE_NAME}" >&2
      echo "${POLICY_RESPONSE}"
      exit 1
  fi
  echo "Policy created successfully."
  # Extract the policy ARN from the response
  POLICY_ARN=$(echo "${POLICY_RESPONSE}" | jq -r '.Policy.Arn')
fi
echo "Using policy: \"${POLICY_ARN}\""

if $skip_role_policy_attachment; then
  echo "Skipping role policy attachment."
else
  arg_errors=()
  [ -z "${ROLE_ARN}" ] && arg_errors+=("ROLE_ARN")
  [ -z "${POLICY_ARN}" ] && arg_errors+=("POLICY_ARN")

  if [ ${#arg_errors[@]} -gt 0 ]; then
    missing_args_string=""
    for i in "${!arg_errors[@]}"; do
      if [ -d "${missing_args_string}" ]; then missing_args_string+=" and "; fi
      missing_args_string+="${arg_errors[$i]}"
    done
    echo "Failed to attach policy to role. Missing ${missing_args_string}"
  fi

  echo "Attaching \"${POLICY_ARN}\" to \"${ROLE_ARN}\"..."
  # Attach the policy to the role using the extracted policy ARN
  if ! ATTACH_ROLE_POLICY_RESPONSE=$(aws iam attach-role-policy --role-name "${ROLE_NAME}" --policy-arn "${POLICY_ARN}"); then
      echo "Error: Failed to attach the policy \"${POLICY_ARN}\" to the role \"${ROLE_NAME}\"" >&2
      echo "${ATTACH_ROLE_POLICY_RESPONSE}"
      exit 1
  fi
  echo "Policy successfully attached to the role."
fi

# Create the step function
aws stepfunctions create-state-machine \
  --name "${STEP_FUNCTION_NAME}" \
  --definition "${STEP_FUNCTION_JSON}" \
  --role-arn "${ROLE_ARN}" \
  --no-paginate

