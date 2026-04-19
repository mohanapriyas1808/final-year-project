"""
Uploads the trained XGBoost model to S3 and creates a SageMaker endpoint.
This replaces the local model in app.py with a SageMaker hosted endpoint.

Run: python lambda_function/setup_sagemaker.py

Cost: ~$0.05/hour for ml.t2.medium inference endpoint
Remember to delete after demo: python lambda_function/setup_sagemaker.py delete
"""

import boto3
import os
import sys
import tarfile
import time
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

REGION        = os.environ.get('AWS_REGION', 'ap-south-1')
ACCOUNT_ID    = '868295556072'
ROLE_ARN      = os.environ.get('LAMBDA_ROLE_ARN', '')
S3_BUCKET     = 'smartbus-historical-data'
MODEL_NAME    = 'smartbus-xgboost-model'
ENDPOINT_NAME = 'smartbus-eta-endpoint'
MODEL_FILE    = os.path.join(os.path.dirname(__file__), '..', 'bus_eta_model.json')

s3  = boto3.client('s3', region_name=REGION,
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'])

sm  = boto3.client('sagemaker', region_name=REGION,
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'])


def upload_model():
    """Package model.json into model.tar.gz and upload to S3."""
    tar_path = os.path.join(os.path.dirname(__file__), 'model.tar.gz')
    with tarfile.open(tar_path, 'w:gz') as tar:
        tar.add(MODEL_FILE, arcname='xgboost-model')
    s3.upload_file(tar_path, S3_BUCKET, 'models/bus_eta_model.tar.gz')
    s3_uri = f"s3://{S3_BUCKET}/models/bus_eta_model.tar.gz"
    print(f"[S3] Model uploaded: {s3_uri}")
    return s3_uri


def create_model(s3_uri):
    """Register model in SageMaker using built-in XGBoost container."""
    # Correct SageMaker XGBoost image for ap-south-1
    image_uri = f"720646828776.dkr.ecr.{REGION}.amazonaws.com/sagemaker-xgboost:1.7-1"
    try:
        sm.create_model(
            ModelName=MODEL_NAME,
            PrimaryContainer={
                'Image':        image_uri,
                'ModelDataUrl': s3_uri,
                'Environment': {}
            },
            ExecutionRoleArn=ROLE_ARN
        )
        print(f"[SAGEMAKER] Model registered: {MODEL_NAME}")
    except Exception as e:
        if 'already exists' in str(e):
            print(f"[SAGEMAKER] Model already exists: {MODEL_NAME}")
        else:
            raise


def create_endpoint():
    """Create serverless endpoint config and deploy endpoint."""
    config_name = f"{MODEL_NAME}-config"

    try:
        sm.create_endpoint_config(
            EndpointConfigName=config_name,
            ProductionVariants=[{
                'VariantName':  'AllTraffic',
                'ModelName':    MODEL_NAME,
                'ServerlessConfig': {
                    'MemorySizeInMB': 1024,   # min memory for XGBoost
                    'MaxConcurrency': 5        # max parallel requests
                }
            }]
        )
        print(f"[SAGEMAKER] Serverless endpoint config created")
    except Exception as e:
        if 'already exists' not in str(e):
            raise

    try:
        sm.create_endpoint(
            EndpointName=ENDPOINT_NAME,
            EndpointConfigName=config_name
        )
        print(f"[SAGEMAKER] Serverless endpoint creating: {ENDPOINT_NAME}")
        print(f"[SAGEMAKER] Waiting for endpoint (~3 mins)...")
        waiter = sm.get_waiter('endpoint_in_service')
        waiter.wait(EndpointName=ENDPOINT_NAME)
        print(f"[SAGEMAKER] Serverless endpoint ready: {ENDPOINT_NAME}")
    except Exception as e:
        if 'already exists' not in str(e):
            raise
        print(f"[SAGEMAKER] Endpoint already exists: {ENDPOINT_NAME}")


def delete_resources():
    """Delete SageMaker endpoint, config and model to stop charges."""
    print("Deleting SageMaker resources...\n")
    config_name = f"{MODEL_NAME}-config"

    for fn, name in [
        (sm.delete_endpoint,        ENDPOINT_NAME),
        (sm.delete_endpoint_config, config_name),
        (sm.delete_model,           MODEL_NAME)
    ]:
        try:
            fn(**{list(fn.__code__.co_varnames[:1])[0]: name} if False else
               ({'EndpointName': name} if 'endpoint' in fn.__name__.lower() and 'config' not in fn.__name__.lower()
                else {'EndpointConfigName': name} if 'config' in fn.__name__.lower()
                else {'ModelName': name}))
            print(f"[DELETED] {name}")
        except Exception as e:
            print(f"[SKIP] {name}: {e}")

    print("\nAll SageMaker resources deleted. No more charges.")


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'delete':
        delete_resources()
    else:
        print("Setting up SageMaker endpoint...\n")
        s3_uri = upload_model()
        create_model(s3_uri)
        create_endpoint()
        print(f"\n✅ Done! Endpoint: {ENDPOINT_NAME}")
        print(f"Update SAGEMAKER_ENDPOINT in .env:")
        print(f"  SAGEMAKER_ENDPOINT={ENDPOINT_NAME}")
        print(f"\nTo delete after demo:")
        print(f"  python lambda_function/setup_sagemaker.py delete")
