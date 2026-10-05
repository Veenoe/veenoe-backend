mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::165835313361:role/mock-runtime"
    }
  }
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "165835313361"
    }
  }
  mock_data "aws_region" {
    defaults = {
      name = "ap-south-1"
    }
  }
}

run "dev_sessions" {
  command = plan
  variables {
    environment = "dev"
  }
  assert {
    condition     = aws_dynamodb_table.sessions.name == "veenoe-dev-sessions"
    error_message = "DEV must use its own table."
  }
  assert {
    condition     = aws_lambda_function.backend.environment[0].variables.DYNAMODB_TABLE_NAME == "veenoe-dev-sessions"
    error_message = "DEV Lambda must receive the DEV table name."
  }
  assert {
    condition     = aws_dynamodb_table.sessions.hash_key == "pk" && aws_dynamodb_table.sessions.range_key == "sk"
    error_message = "Session table must use composite owner/session keys."
  }
  assert {
    condition     = aws_dynamodb_table.sessions.billing_mode == "PROVISIONED" && aws_dynamodb_table.sessions.read_capacity == 5 && aws_dynamodb_table.sessions.write_capacity == 5
    error_message = "Prototype capacity must retain the deliberate 5/5 allocation."
  }
  assert {
    condition     = length(aws_dynamodb_table.sessions.global_secondary_index) == 0 && length(aws_dynamodb_table.sessions.local_secondary_index) == 0
    error_message = "Current access patterns need no indexes."
  }
}

run "prod_sessions" {
  command = plan
  variables {
    environment = "prod"
  }
  assert {
    condition     = aws_dynamodb_table.sessions.name == "veenoe-prod-sessions"
    error_message = "PROD must use its own table."
  }
  assert {
    condition     = aws_lambda_function.backend.environment[0].variables.DYNAMODB_TABLE_NAME == "veenoe-prod-sessions"
    error_message = "PROD Lambda must receive the PROD table name."
  }
  assert {
    condition     = aws_dynamodb_table.sessions.deletion_protection_enabled
    error_message = "PROD table must have deletion protection."
  }
}
