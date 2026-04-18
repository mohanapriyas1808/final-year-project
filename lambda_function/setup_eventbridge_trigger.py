"""
Creates an EventBridge rule that triggers SmartBus_PredictionLambda
every 1 minute — matching the architecture diagram.

Run: python lambda_function/setup_eventbridge_trigger.py
"""

import boto3
import os
import json
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

REGION        = os.environ.get('AWS_REGION', 'ap-south-1')
FUNCTION_NAME = 'SmartBus_PredictionLambda'
RULE_NAME     = 'SmartBus_PredictionTrigger'
ACCOUNT_ID    = '868295556072'

events_client = boto3.client('events', region_name=REGION,
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'])

lambda_client = boto3.client('lambda', region_name=REGION,
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'])


def create_eventbridge_rule():
    """Create a scheduled EventBridge rule — every 1 minute."""
    resp = events_client.put_rule(
        Name=RULE_NAME,
        ScheduleExpression='rate(1 minute)',
        State='ENABLED',
        Description='Triggers SmartBus_PredictionLambda every minute to fetch DynamoDB data and predict ETA'
    )
    rule_arn = resp['RuleArn']
    print(f"[EVENTBRIDGE] Rule created: {RULE_NAME}")
    print(f"[EVENTBRIDGE] ARN: {rule_arn}")
    return rule_arn


def add_lambda_target(rule_arn):
    """Set SmartBus_PredictionLambda as the target of the rule."""
    function_arn = f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:{FUNCTION_NAME}"

    events_client.put_targets(
        Rule=RULE_NAME,
        Targets=[
            {
                'Id':  'PredictionLambdaTarget',
                'Arn': function_arn,
                'Input': json.dumps({'source': 'eventbridge', 'rule': RULE_NAME})
            }
        ]
    )
    print(f"[EVENTBRIDGE] Target set: {FUNCTION_NAME}")
    return function_arn


def grant_eventbridge_permission(rule_arn):
    """Allow EventBridge to invoke the Lambda function."""
    try:
        lambda_client.add_permission(
            FunctionName=FUNCTION_NAME,
            StatementId='EventBridgeInvoke',
            Action='lambda:InvokeFunction',
            Principal='events.amazonaws.com',
            SourceArn=rule_arn
        )
        print(f"[PERMISSION] EventBridge allowed to invoke {FUNCTION_NAME}")
    except lambda_client.exceptions.ResourceConflictException:
        print(f"[PERMISSION] Already exists — skipping")


if __name__ == '__main__':
    print("Setting up EventBridge trigger...\n")
    rule_arn     = create_eventbridge_rule()
    function_arn = add_lambda_target(rule_arn)
    grant_eventbridge_permission(rule_arn)

    print("\nDone. Flow:")
    print("  Driver GPS → Flask → DataIngestion Lambda → SmartBus_NotificationLog + S3")
    print("  → EventBridge (every 1 min) → PredictionLambda → fetches DynamoDB")
    print("  → calls Flask /api/predict_eta → XGBoost ETA → SNS Alert")
