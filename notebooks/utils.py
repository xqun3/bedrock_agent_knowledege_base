import json
import logging
import time
import pprint
import io
import zipfile
from botocore.exceptions import ClientError

logging.basicConfig(format='[%(asctime)s] p%(process)s {%(filename)s:%(lineno)d} %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def create_role(iam, role_name, allowed_services):
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": service},
                "Action": "sts:AssumeRole",
            }
            for service in allowed_services
        ],
    }

    try:
        role = iam.create_role(
            RoleName=role_name, AssumeRolePolicyDocument=json.dumps(trust_policy)
        )
        logger.info("Created role %s.", role.name)
    except ClientError:
        logger.exception("Couldn't create role %s.", role_name)
        raise
    else:
        return role


def get_role(iam, role_name):
    try:
        role = iam.Role(role_name)
        role.load()  # calls GetRole to load attributes
        logger.info("Got role with arn %s.", role.arn)
    except ClientError:
        logger.exception("Couldn't get role named %s.", role_name)
        raise
    else:
        return role


def attach_policy(iam, role_name, policy_arn):
    try:
        iam.Role(role_name).attach_policy(PolicyArn=policy_arn)
        logger.info("Attached policy %s to role %s.", policy_arn, role_name)
    except ClientError:
        logger.exception("Couldn't attach policy %s to role %s.", policy_arn, role_name)
        raise


def create_policy(iam, name, description, actions, resource_arn):
    policy_doc = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": actions, "Resource": resource_arn}],
    }
    try:
        policy = iam.create_policy(
            PolicyName=name,
            Description=description,
            PolicyDocument=json.dumps(policy_doc),
        )
        logger.info("Created policy %s.", policy.arn)
    except ClientError:
        logger.exception("Couldn't create policy %s.", name)
        raise
    else:
        return policy



def createEncryptionPolicy(client, collection_name):
    """Creates an encryption policy that matches all collections beginning with bedrock-knowledge-*"""
    try:
        response = client.create_security_policy(
            description=f'Encryption policy for {collection_name} collections',
            name='bedrock-kb-demo-policy',
            policy="""
                {
                    \"Rules\":[
                        {
                            \"ResourceType\":\"collection\",
                            \"Resource\":[
                                \"collection\/bedrock-knowledge-*\"
                            ]
                        }
                    ],
                    \"AWSOwnedKey\":true
                }
                """,
            type='encryption'
        )
        print('\nEncryption policy created:')
        print(response)
    except ClientError as error:
        if error.response['Error']['Code'] == 'ConflictException':
            print(
                '[ConflictException] The policy name or rules conflict with an existing policy.')
        else:
            raise error

def createNetworkPolicy(client, collection_name):
    """Creates a network policy that matches all collections beginning with bedrock-knowledge-*"""
    try:
        response = client.create_security_policy(
            description=f'Network policy for {collection_name} collections',
            name='bedrock-kb-demo-policy-policy',
            policy="""
                [{
                    \"Description\":\"Public access for TV collection\",
                    \"Rules\":[
                        {
                            \"ResourceType\":\"dashboard\",
                            \"Resource\":[\"collection\/bedrock-knowledge-*\"]
                        },
                        {
                            \"ResourceType\":\"collection\",
                            \"Resource\":[\"collection\/bedrock-knowledge-*\"]
                        }
                    ],
                    \"AllowFromPublic\":true
                }]
                """,
            type='network'
        )
        print('\nNetwork policy created:')
        print(response)
    except ClientError as error:
        if error.response['Error']['Code'] == 'ConflictException':
            print(
                '[ConflictException] A network policy with this name already exists.')
        else:
            raise error

def createCollection(client, collection_name):
    """Creates a collection"""
    try:
        response = client.create_collection(
            name=collection_name,
            type='VECTORSEARCH'
        )
        return(response)
    except ClientError as error:
        if error.response['Error']['Code'] == 'ConflictException':
            print(
                '[ConflictException] A collection with this name already exists. Try another name.')
        else:
            raise error


def waitForCollectionCreation(client, collection_name):
    """Waits for the collection to become active"""
    response = client.batch_get_collection(
        names=[collection_name])
    # Periodically check collection status
    print(response)
    while (response['collectionDetails'][0]['status']) == 'CREATING':
        print('Creating collection...')
        time.sleep(30)
        response = client.batch_get_collection(
            names=[collection_name])
    print('\nCollection successfully created:')
    print(response["collectionDetails"])
    # Extract the collection endpoint from the response
    host = (response['collectionDetails'][0]['collectionEndpoint'])
    collectionarn = (response['collectionDetails'][0]['arn'])
    final_host = host.replace("https://", "")
    return final_host, collectionarn


def create_deployment_package(
        source_file,
        destination_file):
    """
    Creates a Lambda deployment package in .zip format in an in-memory buffer. This
    buffer can be passed directly to Lambda when creating the function.

    :param source_file: The name of the file that contains the Lambda handler
                        function.
    :param destination_file: The name to give the file when it's deployed to Lambda.
    :return: The deployment package.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.write(source_file, destination_file)
    buffer.seek(0)
    return buffer.read()

def create_function(
        lambda_client,
        function_name, 
        handler_name,
        iam_role,
        deployment_package
    ):
    """
    Deploys a Lambda function.

    :param function_name: The name of the Lambda function.
    :param handler_name: The fully qualified name of the handler function. This
                            must include the file name and the function name.
    :param iam_role: The IAM role to use for the function.
    :param deployment_package: The deployment package that contains the function
                                code in .zip format.
    :return: The Amazon Resource Name (ARN) of the newly created function.
    """
    try:
        response = lambda_client.create_function(
            FunctionName=function_name,
            Description="AWS Lambda demo example",
            Runtime="python3.11",
            Role=iam_role.arn,
            Handler=handler_name,
            Code={"ZipFile": deployment_package},
            Publish=True,
        )
        function_arn = response["FunctionArn"]
        waiter = lambda_client.get_waiter("function_active_v2")
        waiter.wait(FunctionName=function_name)
        logger.info(
            "Created function '%s' with ARN: '%s'.",
            function_name,
            response["FunctionArn"],
        )
    except ClientError:
        logger.error("Couldn't create function %s.", function_name)
        raise
    else:
        return function_arn