"""
Deploys prediction_lambda.py to AWS Lambda.
Run: python lambda_function/deploy_prediction_lambda.py
"""

import boto3, zipfile, os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

REGION        = os.environ.get('AWS_REGION', 'ap-south-1')
FUNCTION_NAME = 'SmartBus_PredictionLambda'
HANDLER       = 'prediction_lambda.lambda_handler'
RUNTIME       = 'python3.12'
ROLE_ARN      = os.environ.get('LAMBDA_ROLE_ARN', '')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')

# IMPORTANT: set this to your machine's IP or ngrok URL
# e.g. http://192.168.1.5:5000  or  https://xxxx.ngrok.io
FLASK_URL = os.environ.get('FLASK_URL', 'http://localhost:5000')

lambda_client = boto3.client('lambda', region_name=REGION,
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'])

SOURCE = os.path.join(os.path.dirname(__file__), 'prediction_lambda.py')
ZIP    = os.path.join(os.path.dirname(__file__), 'prediction_lambda.zip')

def build_zip():
    with zipfile.ZipFile(ZIP, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(SOURCE, 'prediction_lambda.py')
    print(f"[ZIP] Built: {ZIP}")
    with open(ZIP, 'rb') as f:
        return f.read()

def deploy(zip_bytes):
    env_vars = {
        'SNS_TOPIC_ARN': SNS_TOPIC_ARN,
        'FLASK_URL':     FLASK_URL,
    }
    try:
        lambda_client.update_function_code(FunctionName=FUNCTION_NAME, ZipFile=zip_bytes)
        # Wait for code update to complete before updating config
        waiter = lambda_client.get_waiter('function_updated')
        waiter.wait(FunctionName=FUNCTION_NAME)
        lambda_client.update_function_configuration(
            FunctionName=FUNCTION_NAME,
            Environment={'Variables': env_vars}
        )
        print(f"[LAMBDA] Updated: {FUNCTION_NAME}")
    except lambda_client.exceptions.ResourceNotFoundException:
        lambda_client.create_function(
            FunctionName=FUNCTION_NAME,
            Runtime=RUNTIME,
            Role=ROLE_ARN,
            Handler=HANDLER,
            Code={'ZipFile': zip_bytes},
            Timeout=30,
            MemorySize=128,
            Environment={'Variables': env_vars}
        )
        print(f"[LAMBDA] Created: {FUNCTION_NAME}")

if __name__ == '__main__':
    deploy(build_zip())
    print("Done.")
