import boto3, os, time
from dotenv import load_dotenv
load_dotenv('.env')

logs = boto3.client('logs', region_name='ap-south-1',
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'])

for fn in ['SmartBus_PredictionLambda', 'SmartBus_GeoFencing']:
    print(f"\n=== {fn} ===")
    try:
        streams = logs.describe_log_streams(
            logGroupName=f'/aws/lambda/{fn}',
            orderBy='LastEventTime', descending=True, limit=1
        ).get('logStreams', [])
        if not streams:
            print("No logs yet")
            continue
        events = logs.get_log_events(
            logGroupName=f'/aws/lambda/{fn}',
            logStreamName=streams[0]['logStreamName'],
            limit=20
        ).get('events', [])
        for e in events:
            print(e['message'].strip())
    except Exception as ex:
        print(f"Error: {ex}")
