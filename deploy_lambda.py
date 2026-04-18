"""
Deploy SmartBus Lambda to AWS ap-south-1
Run: python deploy_lambda.py
"""

import boto3, json, zipfile, os, time
from dotenv import load_dotenv
load_dotenv()

AWS_ACCESS_KEY  = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY  = os.environ.get('AWS_SECRET_ACCESS_KEY')
REGION          = os.environ.get('AWS_REGION', 'ap-south-1')
ACCOUNT_ID      = "868295556072"
FUNCTION_NAME   = "SmartBus_DataProcessor"
ROLE_NAME       = "SmartBus_LambdaRole"

iam    = boto3.client('iam',    aws_access_key_id=AWS_ACCESS_KEY, aws_secret_access_key=AWS_SECRET_KEY, region_name=REGION)
lam    = boto3.client('lambda', aws_access_key_id=AWS_ACCESS_KEY, aws_secret_access_key=AWS_SECRET_KEY, region_name=REGION)

# ── Step 1: Create IAM Role ───────────────────────────────────────────────────
trust_policy = json.dumps({
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "lambda.amazonaws.com"},
        "Action": "sts:AssumeRole"
    }]
})

try:
    role = iam.create_role(
        RoleName=ROLE_NAME,
        AssumeRolePolicyDocument=trust_policy,
        Description="Role for SmartBus Lambda - DynamoDB + SNS access"
    )
    role_arn = role['Role']['Arn']
    print(f"Created IAM Role: {role_arn}")
except iam.exceptions.EntityAlreadyExistsException:
    role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/{ROLE_NAME}"
    print(f"IAM Role already exists: {role_arn}")

# Attach policies: DynamoDB full + SNS full + basic Lambda logs
for policy in [
    "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess",
    "arn:aws:iam::aws:policy/AmazonSNSFullAccess",
    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
]:
    try:
        iam.attach_role_policy(RoleName=ROLE_NAME, PolicyArn=policy)
        print(f"Attached: {policy.split('/')[-1]}")
    except Exception as e:
        print(f"Policy attach note: {e}")

print("Waiting 10s for IAM role to propagate...")
time.sleep(10)

# ── Step 2: Zip Lambda code ───────────────────────────────────────────────────
zip_path = "lambda_function/lambda_function.zip"
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.write("lambda_function/lambda_function.py", "lambda_function.py")
print(f"Zipped Lambda code: {zip_path}")

# ── Step 3: Deploy Lambda ─────────────────────────────────────────────────────
with open(zip_path, 'rb') as f:
    zip_bytes = f.read()

existing_functions = [fn['FunctionName'] for fn in lam.list_functions()['Functions']]

if FUNCTION_NAME not in existing_functions:
    response = lam.create_function(
        FunctionName=FUNCTION_NAME,
        Runtime='python3.12',
        Role=role_arn,
        Handler='lambda_function.lambda_handler',
        Code={'ZipFile': zip_bytes},
        Description='SmartBus data processing layer: ETA calc, geofence check, SNS alerts',
        Timeout=30,
        MemorySize=256,
        Environment={
            'Variables': {
                'REGION':        REGION,
                'SNS_TOPIC_ARN': 'arn:aws:sns:ap-south-1:868295556072:SmartBusNotifications',
                'USERS_TABLE':   'SmartBus_Users',
                'LOG_TABLE':     'SmartBus_NotificationLog'
            }
        }
    )
    print(f"Lambda created: {response['FunctionArn']}")
else:
    response = lam.update_function_code(
        FunctionName=FUNCTION_NAME,
        ZipFile=zip_bytes
    )
    print(f"Lambda updated: {response['FunctionArn']}")

print("\nDone! Lambda is live at ap-south-1.")
print(f"Function name: {FUNCTION_NAME}")
