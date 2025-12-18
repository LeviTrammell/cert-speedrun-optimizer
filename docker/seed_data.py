#!/usr/bin/env python3
"""Seed sample certification exam data for demo purposes."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from cert_speedrun.db.database import ensure_db_exists
from cert_speedrun.db.repository import Repository


async def seed_sample_data():
    """Create a sample AWS SAA exam with topics and questions."""
    await ensure_db_exists()

    # Check if data already exists
    existing = await Repository.get_exam_by_name("AWS Solutions Architect Associate")
    if existing:
        print("Sample data already exists, skipping...")
        return

    # Create sample exam
    exam = await Repository.create_exam(
        name="AWS Solutions Architect Associate",
        vendor="AWS",
        exam_code="SAA-C03",
        description="Sample exam demonstrating the cert-speedrun methodology. Practice questions for AWS Solutions Architect Associate certification.",
        passing_score=72,
        time_limit_minutes=130,
    )
    print(f"Created exam: {exam['name']}")

    # Create topics
    topics = {}
    topic_data = [
        ("Compute", "EC2, Lambda, ECS, and compute services", 20),
        ("Storage", "S3, EBS, EFS, and storage solutions", 18),
        ("Networking", "VPC, Route 53, CloudFront, and networking", 22),
        ("Security", "IAM, KMS, security best practices", 20),
        ("Database", "RDS, DynamoDB, database solutions", 20),
    ]

    for name, desc, weight in topic_data:
        topic = await Repository.create_topic(
            exam_id=exam["id"],
            name=name,
            description=desc,
            weight_percent=weight,
        )
        topics[name] = topic["id"]
        print(f"  Created topic: {name}")

    # Create sample questions with bias-free answers
    sample_questions = [
        {
            "question_text": "A company needs to store infrequently accessed data that must be retrievable within milliseconds. Which S3 storage class should they use?",
            "topic_ids": [topics["Storage"]],
            "difficulty": "easy",
            "explanation": "S3 Standard-IA is designed for data that is accessed less frequently but requires rapid access when needed. It offers millisecond retrieval times unlike Glacier classes.",
            "answers": [
                {"text": "S3 Standard-Infrequent Access (S3 Standard-IA)", "is_correct": True},
                {"text": "S3 Glacier Instant Retrieval for long-term archival", "is_correct": False, "distractor_reason": "Glacier is for archival, not immediate access patterns"},
                {"text": "S3 One Zone-IA with cross-region replication enabled", "is_correct": False, "distractor_reason": "One Zone-IA has lower durability due to single AZ"},
                {"text": "S3 Intelligent-Tiering with archive access tier", "is_correct": False, "distractor_reason": "Archive tier does not provide millisecond retrieval"},
            ],
        },
        {
            "question_text": "A web application requires a relational database with automatic failover and read replicas. Which AWS service should the solutions architect recommend?",
            "topic_ids": [topics["Database"]],
            "difficulty": "easy",
            "explanation": "Amazon RDS Multi-AZ provides automatic failover to a standby replica, while read replicas can be created for read scaling.",
            "answers": [
                {"text": "Amazon RDS with Multi-AZ deployment enabled", "is_correct": True},
                {"text": "Amazon DynamoDB with global tables configured", "is_correct": False, "distractor_reason": "DynamoDB is NoSQL, not relational database"},
                {"text": "Amazon Redshift with cluster resize capability", "is_correct": False, "distractor_reason": "Redshift is for analytics, not transactional workloads"},
                {"text": "Amazon ElastiCache with replication group setup", "is_correct": False, "distractor_reason": "ElastiCache is for caching, not primary database"},
            ],
        },
        {
            "question_text": "An application needs to process messages asynchronously with guaranteed delivery and the ability to delay message processing. Which service combination should be used?",
            "topic_ids": [topics["Compute"]],
            "difficulty": "medium",
            "explanation": "SQS provides reliable message queuing with built-in delay queues. Lambda can process messages when they become available.",
            "answers": [
                {"text": "Amazon SQS with delay queues and AWS Lambda", "is_correct": True},
                {"text": "Amazon SNS with message filtering and Lambda", "is_correct": False, "distractor_reason": "SNS is pub/sub, does not support message delays"},
                {"text": "Amazon Kinesis Data Streams with EC2 consumers", "is_correct": False, "distractor_reason": "Kinesis is for streaming, not delayed processing"},
                {"text": "Amazon EventBridge with scheduled rule targets", "is_correct": False, "distractor_reason": "EventBridge rules are time-based, not message delays"},
            ],
        },
        {
            "question_text": "A company needs to restrict access to an S3 bucket so that only users from a specific VPC can access it. What should the solutions architect implement?",
            "topic_ids": [topics["Security"], topics["Storage"]],
            "difficulty": "medium",
            "explanation": "VPC endpoints for S3 combined with bucket policies using the aws:sourceVpce condition restrict access to specific VPCs.",
            "answers": [
                {"text": "VPC endpoint for S3 with bucket policy condition", "is_correct": True},
                {"text": "S3 Access Points with network origin controls set", "is_correct": False, "distractor_reason": "Access Points require additional configuration beyond VPC"},
                {"text": "IAM policies with IP address range restrictions", "is_correct": False, "distractor_reason": "IP restrictions don't work well with VPC private IPs"},
                {"text": "Security groups attached to the S3 bucket directly", "is_correct": False, "distractor_reason": "S3 doesn't support security groups attachment"},
            ],
        },
        {
            "question_text": "An application running on EC2 instances needs to access DynamoDB tables. What is the most secure way to grant this access?",
            "topic_ids": [topics["Security"], topics["Compute"]],
            "difficulty": "easy",
            "explanation": "IAM roles for EC2 instances provide temporary credentials automatically rotated, eliminating the need to store long-term credentials.",
            "answers": [
                {"text": "Attach an IAM role to the EC2 instances", "is_correct": True},
                {"text": "Store IAM access keys in environment variables", "is_correct": False, "distractor_reason": "Access keys are long-term credentials, less secure"},
                {"text": "Use AWS Secrets Manager to store access keys", "is_correct": False, "distractor_reason": "Still requires managing access keys unnecessarily"},
                {"text": "Create IAM users for each EC2 instance deployed", "is_correct": False, "distractor_reason": "IAM users with access keys are less secure than roles"},
            ],
        },
        {
            "question_text": "A company wants to serve static content globally with low latency. The content is stored in S3. Which architecture should be implemented?",
            "topic_ids": [topics["Networking"], topics["Storage"]],
            "difficulty": "easy",
            "explanation": "CloudFront is AWS's CDN service that caches content at edge locations globally, reducing latency for users worldwide.",
            "answers": [
                {"text": "CloudFront distribution with S3 bucket as origin", "is_correct": True},
                {"text": "S3 Transfer Acceleration with multi-region buckets", "is_correct": False, "distractor_reason": "Transfer Acceleration is for uploads, not serving"},
                {"text": "Global Accelerator with S3 endpoint configured", "is_correct": False, "distractor_reason": "Global Accelerator is for TCP/UDP, not static content"},
                {"text": "Route 53 geolocation routing to regional S3 buckets", "is_correct": False, "distractor_reason": "Requires managing multiple buckets, no edge caching"},
            ],
        },
        {
            "question_text": "An application needs to track user sessions across multiple EC2 instances behind an Application Load Balancer. What should the solutions architect implement?",
            "topic_ids": [topics["Compute"], topics["Database"]],
            "difficulty": "medium",
            "explanation": "ElastiCache provides an external session store that all instances can access, enabling stateless application design.",
            "answers": [
                {"text": "Amazon ElastiCache for session state storage", "is_correct": True},
                {"text": "ALB sticky sessions with application cookies set", "is_correct": False, "distractor_reason": "Sticky sessions reduce load distribution effectiveness"},
                {"text": "Store sessions on EBS volumes attached to each EC2", "is_correct": False, "distractor_reason": "EBS is instance-specific, not shared across instances"},
                {"text": "Use EC2 instance store for temporary session data", "is_correct": False, "distractor_reason": "Instance store is ephemeral and instance-specific"},
            ],
        },
        {
            "question_text": "A company needs to encrypt data at rest in an RDS database and manage the encryption keys themselves. Which solution meets this requirement?",
            "topic_ids": [topics["Database"], topics["Security"]],
            "difficulty": "medium",
            "explanation": "RDS supports encryption using customer-managed keys (CMK) stored in AWS KMS, giving customers control over key management.",
            "answers": [
                {"text": "Enable RDS encryption with a customer-managed KMS key", "is_correct": True},
                {"text": "Use AWS CloudHSM to store database encryption keys", "is_correct": False, "distractor_reason": "CloudHSM is not directly integrated with RDS encryption"},
                {"text": "Implement client-side encryption before storing in RDS", "is_correct": False, "distractor_reason": "Client-side encryption complicates queries and indexing"},
                {"text": "Store encryption keys in AWS Secrets Manager service", "is_correct": False, "distractor_reason": "Secrets Manager stores secrets, not encryption keys for RDS"},
            ],
        },
    ]

    for q in sample_questions:
        await Repository.create_question(
            exam_id=exam["id"],
            question_text=q["question_text"],
            question_type="single",
            answers=q["answers"],
            topic_ids=q.get("topic_ids"),
            difficulty=q.get("difficulty", "medium"),
            explanation=q.get("explanation"),
        )

    print(f"\nCreated {len(sample_questions)} sample questions")
    print(f"\nSample exam ready: {exam['name']}")


if __name__ == "__main__":
    asyncio.run(seed_sample_data())
