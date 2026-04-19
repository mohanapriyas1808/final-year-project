"""
Creates a CloudWatch Dashboard for SmartBus monitoring.
Shows Lambda invocations, errors, duration for all 3 Lambda functions.

Run: python lambda_function/setup_cloudwatch_dashboard.py
Then view at: AWS Console → CloudWatch → Dashboards → SmartBusDashboard
"""

import boto3
import os
import json
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

REGION         = os.environ.get('AWS_REGION', 'ap-south-1')
DASHBOARD_NAME = 'SmartBusDashboard'

cw = boto3.client('cloudwatch', region_name=REGION,
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'])

LAMBDAS = [
    'SmartBus_DataIngestion',
    'SmartBus_PredictionLambda',
    'SmartBus_GeoFencing'
]

dashboard_body = {
    "widgets": [
        # --- Title ---
        {
            "type": "text",
            "x": 0, "y": 0, "width": 24, "height": 1,
            "properties": {
                "markdown": "# SmartBus System Monitor — Lambda Functions"
            }
        },

        # --- Invocations ---
        {
            "type": "metric",
            "x": 0, "y": 1, "width": 8, "height": 6,
            "properties": {
                "title": "Lambda Invocations",
                "view": "timeSeries",
                "metrics": [[
                    "AWS/Lambda", "Invocations",
                    "FunctionName", fn
                ] for fn in LAMBDAS],
                "period": 60,
                "stat": "Sum",
                "region": REGION
            }
        },

        # --- Errors ---
        {
            "type": "metric",
            "x": 8, "y": 1, "width": 8, "height": 6,
            "properties": {
                "title": "Lambda Errors",
                "view": "timeSeries",
                "metrics": [[
                    "AWS/Lambda", "Errors",
                    "FunctionName", fn
                ] for fn in LAMBDAS],
                "period": 60,
                "stat": "Sum",
                "region": REGION
            }
        },

        # --- Duration ---
        {
            "type": "metric",
            "x": 16, "y": 1, "width": 8, "height": 6,
            "properties": {
                "title": "Lambda Duration (ms)",
                "view": "timeSeries",
                "metrics": [[
                    "AWS/Lambda", "Duration",
                    "FunctionName", fn
                ] for fn in LAMBDAS],
                "period": 60,
                "stat": "Average",
                "region": REGION
            }
        },

        # --- DataIngestion Logs ---
        {
            "type": "log",
            "x": 0, "y": 7, "width": 8, "height": 6,
            "properties": {
                "title": "DataIngestion Lambda Logs",
                "query": f"SOURCE '/aws/lambda/SmartBus_DataIngestion' | fields @timestamp, @message | sort @timestamp desc | limit 20",
                "region": REGION,
                "view": "table"
            }
        },

        # --- Prediction Lambda Logs ---
        {
            "type": "log",
            "x": 8, "y": 7, "width": 8, "height": 6,
            "properties": {
                "title": "Prediction Lambda Logs",
                "query": f"SOURCE '/aws/lambda/SmartBus_PredictionLambda' | fields @timestamp, @message | sort @timestamp desc | limit 20",
                "region": REGION,
                "view": "table"
            }
        },

        # --- GeoFencing Lambda Logs ---
        {
            "type": "log",
            "x": 16, "y": 7, "width": 8, "height": 6,
            "properties": {
                "title": "GeoFencing Lambda Logs",
                "query": f"SOURCE '/aws/lambda/SmartBus_GeoFencing' | fields @timestamp, @message | sort @timestamp desc | limit 20",
                "region": REGION,
                "view": "table"
            }
        },

        # --- SNS Alerts sent ---
        {
            "type": "metric",
            "x": 0, "y": 13, "width": 12, "height": 6,
            "properties": {
                "title": "SNS Notifications Published",
                "view": "timeSeries",
                "metrics": [[
                    "AWS/SNS", "NumberOfMessagesSent",
                    "TopicName", "SmartBusNotifications"
                ]],
                "period": 60,
                "stat": "Sum",
                "region": REGION
            }
        },

        # --- DynamoDB reads ---
        {
            "type": "metric",
            "x": 12, "y": 13, "width": 12, "height": 6,
            "properties": {
                "title": "DynamoDB Consumed Read/Write Units",
                "view": "timeSeries",
                "metrics": [
                    ["AWS/DynamoDB", "ConsumedReadCapacityUnits",  "TableName", "SmartBus_Users"],
                    ["AWS/DynamoDB", "ConsumedWriteCapacityUnits", "TableName", "SmartBus_Users"],
                    ["AWS/DynamoDB", "ConsumedReadCapacityUnits",  "TableName", "SmartBus_NotificationLog"],
                    ["AWS/DynamoDB", "ConsumedWriteCapacityUnits", "TableName", "SmartBus_NotificationLog"]
                ],
                "period": 60,
                "stat": "Sum",
                "region": REGION
            }
        }
    ]
}

if __name__ == '__main__':
    cw.put_dashboard(
        DashboardName=DASHBOARD_NAME,
        DashboardBody=json.dumps(dashboard_body)
    )
    print(f"Dashboard created: {DASHBOARD_NAME}")
    print(f"View at: https://{REGION}.console.aws.amazon.com/cloudwatch/home?region={REGION}#dashboards:name={DASHBOARD_NAME}")
