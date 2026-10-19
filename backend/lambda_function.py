import json
import os

import boto3

dynamodb = boto3.client("dynamodb")
TABLE_NAME = os.environ.get("TABLE_NAME", "cloud-resume-visitors")


def lambda_handler(event, context):
    try:
        response = dynamodb.update_item(
            TableName=TABLE_NAME,
            Key={"id": {"S": "visitors"}},
            UpdateExpression="ADD visit_count :inc",
            ExpressionAttributeValues={":inc": {"N": "1"}},
            ReturnValues="UPDATED_NEW",
        )
        count = int(response["Attributes"]["visit_count"]["N"])
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"count": count}),
        }
    except Exception as e:
        print(f"Counter update failed: {e}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "counter unavailable"}),
        }