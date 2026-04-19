"""
Creates API Gateway REST API that triggers SmartBus_DataIngestion Lambda.

Run: python lambda_function/setup_api_gateway.py

After running, update BACKEND_URL in DriverDashboard.js with the API Gateway URL.
"""

import boto3
import os
import json
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

REGION        = os.environ.get('AWS_REGION', 'ap-south-1')
ACCOUNT_ID    = '868295556072'
FUNCTION_NAME = 'SmartBus_DataIngestion'
API_NAME      = 'SmartBusAPI'

apigw = boto3.client('apigateway', region_name=REGION,
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'])

lambda_client = boto3.client('lambda', region_name=REGION,
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'])


def create_api():
    """Create REST API."""
    resp = apigw.create_rest_api(
        name=API_NAME,
        description='SmartBus GPS Data Ingestion API',
        endpointConfiguration={'types': ['REGIONAL']}
    )
    api_id = resp['id']
    print(f"[API] Created: {API_NAME} (id={api_id})")
    return api_id


def get_root_resource(api_id):
    """Get the root resource id."""
    resources = apigw.get_resources(restApiId=api_id)['items']
    return next(r['id'] for r in resources if r['path'] == '/')


def create_resource(api_id, parent_id, path):
    """Create a resource path."""
    resp = apigw.create_resource(
        restApiId=api_id,
        parentId=parent_id,
        pathPart=path
    )
    print(f"[API] Resource created: /{path}")
    return resp['id']


def create_method(api_id, resource_id):
    """Create POST method with no auth."""
    apigw.put_method(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod='POST',
        authorizationType='NONE'
    )
    # Enable CORS — OPTIONS method
    apigw.put_method(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod='OPTIONS',
        authorizationType='NONE'
    )
    print(f"[API] POST + OPTIONS methods created")


def integrate_lambda(api_id, resource_id):
    """Connect POST method to DataIngestion Lambda."""
    function_arn = f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:{FUNCTION_NAME}"
    uri = f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/{function_arn}/invocations"

    # POST → Lambda
    apigw.put_integration(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod='POST',
        type='AWS_PROXY',
        integrationHttpMethod='POST',
        uri=uri
    )

    # OPTIONS → Mock (for CORS)
    apigw.put_integration(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod='OPTIONS',
        type='MOCK',
        requestTemplates={'application/json': '{"statusCode": 200}'}
    )

    # Must create method response BEFORE integration response
    apigw.put_method_response(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod='OPTIONS',
        statusCode='200',
        responseParameters={
            'method.response.header.Access-Control-Allow-Headers': False,
            'method.response.header.Access-Control-Allow-Methods': False,
            'method.response.header.Access-Control-Allow-Origin':  False
        }
    )

    apigw.put_integration_response(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod='OPTIONS',
        statusCode='200',
        responseParameters={
            'method.response.header.Access-Control-Allow-Headers': "'Content-Type'",
            'method.response.header.Access-Control-Allow-Methods': "'POST,OPTIONS'",
            'method.response.header.Access-Control-Allow-Origin':  "'*'"
        }
    )
    print(f"[API] Lambda integration set")


def grant_permission(api_id):
    """Allow API Gateway to invoke the Lambda."""
    function_arn = f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:{FUNCTION_NAME}"
    source_arn   = f"arn:aws:execute-api:{REGION}:{ACCOUNT_ID}:{api_id}/*/POST/ingest"
    try:
        lambda_client.add_permission(
            FunctionName=FUNCTION_NAME,
            StatementId='APIGatewayInvoke',
            Action='lambda:InvokeFunction',
            Principal='apigateway.amazonaws.com',
            SourceArn=source_arn
        )
        print(f"[PERMISSION] API Gateway allowed to invoke {FUNCTION_NAME}")
    except lambda_client.exceptions.ResourceConflictException:
        print(f"[PERMISSION] Already exists")


def deploy_api(api_id):
    """Deploy to 'prod' stage."""
    apigw.create_deployment(restApiId=api_id, stageName='prod')
    url = f"https://{api_id}.execute-api.{REGION}.amazonaws.com/prod/ingest"
    print(f"\n[API] Deployed to prod stage")
    print(f"[API] Endpoint URL: {url}")
    return url


if __name__ == '__main__':
    print("Setting up API Gateway...\n")

    api_id      = create_api()
    root_id     = get_root_resource(api_id)
    resource_id = create_resource(api_id, root_id, 'ingest')

    create_method(api_id, resource_id)
    integrate_lambda(api_id, resource_id)
    grant_permission(api_id)
    url = deploy_api(api_id)

    print(f"\n✅ Done! Update DriverDashboard.js:")
    print(f"   INGEST_URL = '{url}'")
    print(f"\nDriver GPS will now flow:")
    print(f"   Driver → {url} → DataIngestion Lambda → DynamoDB + S3")
