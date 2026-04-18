"""
Run this once to create:
  - S3 bucket: smartbus-historical-data

Existing DynamoDB tables (already created, do NOT recreate):
  - SmartBus_Users
  - SmartBus_BusStops
  - SmartBus_NotificationLog
"""

import boto3
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

REGION    = os.environ.get('AWS_REGION', 'ap-south-1')
S3_BUCKET = 'smartbus-historical-data'

s3 = boto3.client('s3', region_name=REGION,
                   aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
                   aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'])


def create_s3_bucket():
    try:
        s3.create_bucket(
            Bucket=S3_BUCKET,
            CreateBucketConfiguration={'LocationConstraint': REGION}
        )
        s3.put_public_access_block(
            Bucket=S3_BUCKET,
            PublicAccessBlockConfiguration={
                'BlockPublicAcls': True,
                'IgnorePublicAcls': True,
                'BlockPublicPolicy': True,
                'RestrictPublicBuckets': True
            }
        )
        print(f"[S3] Created bucket: {S3_BUCKET}")
    except s3.exceptions.BucketAlreadyOwnedByYou:
        print(f"[S3] Bucket already exists: {S3_BUCKET}")
    except Exception as e:
        print(f"[S3 ERROR] {e}")


if __name__ == '__main__':
    print("Creating S3 bucket...")
    create_s3_bucket()
    print("Done.")
