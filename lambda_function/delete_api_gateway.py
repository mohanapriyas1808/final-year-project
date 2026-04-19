import boto3, os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

REGION = os.environ.get('AWS_REGION', 'ap-south-1')
apigw  = boto3.client('apigateway', region_name=REGION,
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'])

apis = apigw.get_rest_apis()['items']
for api in apis:
    if api['name'] == 'SmartBusAPI':
        apigw.delete_rest_api(restApiId=api['id'])
        print(f"Deleted: {api['name']} ({api['id']})")
