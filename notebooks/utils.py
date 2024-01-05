import json
import logging
import time
import pprint
import io
import zipfile
import sys
import time
from uuid import uuid4
import boto3
from botocore.exceptions import ClientError

from uuid import uuid4

uuidChars = ("a", "b", "c", "d", "e", "f",
       "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s",
       "t", "u", "v", "w", "x", "y", "z", "0", "1", "2", "3", "4", "5",
       "6", "7", "8", "9")

def short_uuid():
  uuid = str(uuid4()).replace('-', '')
  result = ''
  for i in range(0,8):
    sub = uuid[i * 4: i * 4 + 4]
    x = int(sub,16)
    result += uuidChars[x % 0x24]
  return result


def progress_bar(seconds):
    """Shows a simple progress bar in the command window."""
    for _ in range(seconds):
        time.sleep(1)
        print(".", end="")
        sys.stdout.flush()
    print()

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



def createEncryptionPolicy(client, collection_name, id):
    name = f'bedrock-kb-demo-{id}'
    policy=json.dumps({
        "Rules":
        [
            {
                "ResourceType":"collection",
                "Resource":[f"collection/{collection_name}"]
            }
        ],
        "AWSOwnedKey":True
        })
    print(policy)
    try:
        response = client.create_security_policy(
            description=f'Encryption policy for {collection_name} collections',
            name=name,
            policy=policy,
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
    return name

def createNetworkPolicy(client, collection_name, id):
    """Creates a network policy that matches all collections beginning with bedrock-knowledge-*"""
    name = f'bedrock-kb-demo-{id}'
    policy=[
        {
            "Description":"Public access for TV collection",
            "Rules":[
                {
                    "ResourceType":"dashboard",
                    "Resource":[f"collection/{collection_name}"]
                },
                {
                    "ResourceType":"collection",
                    "Resource":[f"collection/{collection_name}"]
                }
            ],
            "AllowFromPublic":True
        }]

    try:
        response = client.create_security_policy(
            description=f'Network policy for {collection_name} collections',
            name=name,
            policy=json.dumps(policy),
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
    return name


def createAccessPolicy(client, index_name, collection_name, role_arn, account_id, id):
    name = f'bedrock-kb-demo-{id}'
    policy = [{
    "Rules":[
                {
                        "Resource":[f"index/{index_name}/*"],
                        "Permission":["aoss:CreateIndex","aoss:DeleteIndex","aoss:UpdateIndex","aoss:DescribeIndex","aoss:ReadDocument","aoss:WriteDocument"],
                        "ResourceType": "index"
                },
                {
                        "Resource":[
                            f"collection/{collection_name}"
                        ],
                        "Permission":[
                            "aoss:CreateCollectionItems",
                            "aoss:DescribeCollectionItems",
                            "aoss:UpdateCollectionItems"
                        ],
                        "ResourceType": "collection"
                }
                ],
                "Principal":[
                    f"{role_arn}",
                    f"arn:aws:iam::{account_id}:role/Admin"
                ]
        }]

    try:
        response = client.create_access_policy(
            description=f'Data access policy for "{collection_name}" collections',
            name=name,
            policy=json.dumps(policy),
            type='data'
        )
        policyVersion = response["accessPolicyDetail"]["policyVersion"]
        print('\nAccess policy created:')
        print(response)
    except ClientError as error:
        if error.response['Error']['Code'] == 'ConflictException':
            print(
                '[ConflictException] An access policy with this name already exists.')
        else:
            raise error
    
    return name, policyVersion


def updateAccessPolicy(
        client,
        index_name,
        collection_name,
        role_arn,
        account_id,
        name,
        bedrock_knowledge_base_role_name,
        policy_version
        ):
    
    policy = [{
        "Rules":[
                    {
                            "Resource":[f"index/{index_name}/*"],
                            "Permission":["aoss:CreateIndex","aoss:DeleteIndex","aoss:UpdateIndex","aoss:DescribeIndex","aoss:ReadDocument","aoss:WriteDocument"],
                            "ResourceType": "index"
                    },
                    {
                            "Resource":[
                                f"collection/{collection_name}"
                            ],
                            "Permission":[
                                "aoss:CreateCollectionItems",
                                "aoss:DescribeCollectionItems",
                                "aoss:UpdateCollectionItems"
                            ],
                            "ResourceType": "collection"
                    }
                    ],
                    "Principal":[
                        f"arn:aws:iam::{account_id}:role/{bedrock_knowledge_base_role_name}",
                        f"{role_arn}",
                        f"arn:aws:iam::{account_id}:role/Admin"
                    ]
            }]
    try:
        response = client.update_access_policy(
            description=f'Data access policy for {collection_name} collections',
            name=name,
            policy=json.dumps(policy),
            type='data',
            policyVersion=policy_version
        )
        print('\nAccess policy updated:')
        print(response)
    except ClientError as error:
        if error.response['Error']['Code'] == 'ConflictException':
            print(
                '[ConflictException] An access policy with this name already exists.')
        else:
            raise error

def createCollection(client, collection_name):
    """Creates a collection"""
    try:
        response = client.create_collection(
            name=collection_name,
            type='VECTORSEARCH'
        )
        print(response)
        # collection_id = response["collectionDetails"]["id"]
        return (response)
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
    host = response['collectionDetails'][0]['collectionEndpoint']
    collectionarn = response['collectionDetails'][0]['arn']
    collection_id = response["collectionDetails"][0]["id"]
    final_host = host.replace("https://", "")
    return final_host, collectionarn, collection_id 


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


def teardown(iam, roles):
    """
    Removes all resources created during setup.

    :param user: The demo user.
    :param role: The demo role.
    """
    try:
        for role in roles:
            for attached in role.attached_policies.all():
                policy_name = attached.policy_name
                role.detach_policy(PolicyArn=attached.arn)
                try:
                    attached.delete()
                except:
                    response = iam.list_policy_versions(PolicyArn=attached.arn)
                    print(response)
                    attached.delete_version()
                    response = iam.delete_policy_version(
                        PolicyArn=attached.arn,
                        VersionId=response['Versions']['VersionId']
                    )
                    print(response)
                print(f"Detached and deleted {policy_name}.")
            role.delete()
            print(f"Deleted {role.name}.")
    except ClientError as error:
        print(
            "Couldn't detach policy, delete policy, or delete role. Here's why: "
            f"{error.response['Error']['Message']}"
        )
        raise
