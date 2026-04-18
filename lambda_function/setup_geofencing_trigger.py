"""
Creates an EventBridge rule that:
  - Listens for 'ETACalculated' events from SmartBus_PredictionLambda
  - Triggers SmartBus_GeoFencing Lambda automatically

Run: python lambda_function/setup_geofencing_trigger.py
"""

import boto3
import os
import json
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

REGION        = os.environ.get('AWS_REGION', 'ap-south-1')
ACCOUNT_ID    = '868295556072'
RULE_NAME     = 'SmartBus_GeoFencingTrigger'
FUNCTION_NAME = 'SmartBus_GeoFencing'

events_client = boto3.client('events', region_name=REGION,
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'])

lambda_client = boto3.client('lambda', region_name=REGION,
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'])


def create_rule():
    """
    Rule pattern: match events from 'smartbus.prediction' source
    with DetailType 'ETACalculated' — published by PredictionLambda.
    """
    resp = events_client.put_rule(
        Name=RULE_NAME,
        EventPattern=json.dumps({
            'source':      ['smartbus.prediction'],
            'detail-type': ['ETACalculated']
        }),
        State='ENABLED',
        Description='Triggers SmartBus_GeoFencing when PredictionLambda publishes ETACalculated event'
    )
    rule_arn = resp['RuleArn']
    print(f"[EVENTBRIDGE] Rule created: {RULE_NAME}")
    print(f"[EVENTBRIDGE] ARN: {rule_arn}")
    return rule_arn


def add_lambda_target(rule_arn):
    """Set SmartBus_GeoFencing as the target."""
    function_arn = f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:{FUNCTION_NAME}"
    events_client.put_targets(
        Rule=RULE_NAME,
        Targets=[{
            'Id':  'GeoFencingTarget',
            'Arn': function_arn
        }]
    )
    print(f"[EVENTBRIDGE] Target set: {FUNCTION_NAME}")
    return function_arn


def grant_permission(rule_arn):
    """Allow EventBridge to invoke the GeoFencing Lambda."""
    try:
        lambda_client.add_permission(
            FunctionName=FUNCTION_NAME,
            StatementId='EventBridgeGeoFencingInvoke',
            Action='lambda:InvokeFunction',
            Principal='events.amazonaws.com',
            SourceArn=rule_arn
        )
        print(f"[PERMISSION] EventBridge allowed to invoke {FUNCTION_NAME}")
    except lambda_client.exceptions.ResourceConflictException:
        print(f"[PERMISSION] Already exists — skipping")


if __name__ == '__main__':
    print("Setting up EventBridge → GeoFencing trigger...\n")
    rule_arn = create_rule()
    add_lambda_target(rule_arn)
    grant_permission(rule_arn)

    print("\nDone. Full flow:")
    print("  EventBridge (1 min) → PredictionLambda → calculates ETA")
    print("  → publishes 'ETACalculated' event to EventBridge")
    print("  → EventBridge rule triggers SmartBus_GeoFencing")
    print("  → dynamic radius check → SNS Arrival Alert")
