"""
Zips and deploys data_ingestion_lambda.py to AWS Lambda.
Run: python lambda_function/deploy_ingestion_lambda.py
"""

import boto3
import zipfile
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

REGION          = os.environ.get('AWS_REGION', 'ap-south-1')
FUNCTION_NAME   = 'SmartBus_DataIngestion'
HANDLER         = 'data_ingestion_lambda.lambda_handler'
RUNTIME         = 'python3.12'
ROLE_ARN        = os.environ.get('LAMBDA_ROLE_ARN', '')   # set in .env
S3_BUCKET       = 'smartbus-historical-data'
BUS_STATE_TABLE = 'SmartBus_BusState'

lambda_client = boto3.client(
    'lambda', region_name=REGION,
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY']
)

SOURCE_FILE = os.path.join(os.path.dirname(__file__), 'data_ingestion_lambda.py')
ZIP_FILE    = os.path.join(os.path.dirname(__file__), 'data_ingestion_lambda.zip')


def build_zip():
    with zipfile.ZipFile(ZIP_FILE, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(SOURCE_FILE, 'data_ingestion_lambda.py')
    print(f"[ZIP] Built: {ZIP_FILE}")
    with open(ZIP_FILE, 'rb') as f:
        return f.read()


def deploy(zip_bytes):
    env_vars = {
        'BUS_STATE_TABLE':  BUS_STATE_TABLE,
        'S3_BUCKET':        S3_BUCKET,
    }

    try:
        # Try update first
        lambda_client.update_function_code(
            FunctionName=FUNCTION_NAME,
            ZipFile=zip_bytes
        )
        lambda_client.update_function_configuration(
            FunctionName=FUNCTION_NAME,
            Environment={'Variables': env_vars}
        )
        print(f"[LAMBDA] Updated: {FUNCTION_NAME}")

    except lambda_client.exceptions.ResourceNotFoundException:
        if not ROLE_ARN:
            print("[ERROR] LAMBDA_ROLE_ARN not set in .env — needed for first deploy")
            return
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
    zip_bytes = build_zip()
    deploy(zip_bytes)
    print("Deployment complete.")
