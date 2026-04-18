import boto3, os
from dotenv import load_dotenv
from botocore.exceptions import ClientError
load_dotenv()

sns = boto3.client('sns',
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
    region_name='ap-south-1')

try:
    res = sns.publish(
        TopicArn='arn:aws:sns:ap-south-1:868295556072:SmartBusNotifications',
        Subject='SmartBus Test',
        Message='Test notification from SmartBus',
        MessageAttributes={'username': {'DataType': 'String', 'StringValue': 'Priya'}}
    )
    print('Success! MessageId:', res['MessageId'])
except ClientError as e:
    print('ClientError:', e.response['Error']['Code'], e.response['Error']['Message'])
except Exception as e:
    print('Exception:', type(e).__name__, str(e))
