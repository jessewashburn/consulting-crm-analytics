# AWS Setup Guide - From Scratch

This guide walks you through setting up AWS resources for the CRM Analytics Service.

## Prerequisites
- AWS Account (free tier is sufficient)
- Credit card for AWS account verification

---

## Step 1: Create AWS Account (if you don't have one)

1. Go to https://aws.amazon.com/
2. Click **"Create an AWS Account"**
3. Follow the signup process:
   - Email and password
   - Contact information
   - Credit card (won't be charged for free tier usage)
   - Phone verification
   - Choose **Basic Support (Free)**

**Free Tier Limits (more than enough for this project):**
- SQS: 1 million requests/month FREE
- S3: 5GB storage, 20,000 GET requests, 2,000 PUT requests/month FREE
- EC2: 750 hours/month t2.micro or t3.micro FREE

---

## Step 2: Install AWS CLI

### Windows (PowerShell as Administrator):
```powershell
# Download installer
$url = "https://awscli.amazonaws.com/AWSCLIV2.msi"
$output = "$env:TEMP\AWSCLIV2.msi"
Invoke-WebRequest -Uri $url -OutFile $output

# Install
Start-Process msiexec.exe -Wait -ArgumentList "/i $output /quiet"

# Verify (restart terminal first)
aws --version
```

### Or use winget:
```powershell
winget install Amazon.AWSCLI
```

---

## Step 3: Create IAM User (Best Practice)

**Never use root credentials for applications!**

### 3.1 Sign in to AWS Console
1. Go to https://console.aws.amazon.com/
2. Sign in with your account

### 3.2 Create IAM User
1. Search for **"IAM"** in the top search bar
2. Click **"Users"** in left sidebar
3. Click **"Create user"**
4. **User name:** `crm-analytics-service`
5. Click **"Next"**

### 3.3 Set Permissions
1. Select **"Attach policies directly"**
2. Search and check these policies:
   - ✅ **AmazonSQSFullAccess**
   - ✅ **AmazonS3FullAccess**
3. Click **"Next"**
4. Click **"Create user"**

### 3.4 Create Access Keys
1. Click on the user you just created: `crm-analytics-service`
2. Go to **"Security credentials"** tab
3. Scroll to **"Access keys"**
4. Click **"Create access key"**
5. Select **"Application running outside AWS"**
6. Click **"Next"**
7. Optional: Add description tag: `CRM Analytics Service`
8. Click **"Create access key"**

**⚠️ CRITICAL: Copy these now - you won't see them again!**
- **Access Key ID:** (starts with `AKIA...`)
- **Secret Access Key:** (long random string)

---

## Step 4: Configure AWS CLI

```bash
aws configure
```

Enter when prompted:
- **AWS Access Key ID:** `[paste your key]`
- **AWS Secret Access Key:** `[paste your secret]`
- **Default region name:** `us-east-1`
- **Default output format:** `json`

**Verify it works:**
```bash
aws sts get-caller-identity
```

You should see your account ID and user ARN.

---

## Step 5: Create SQS Queue

### Option A: Using AWS CLI (Recommended)
```bash
# Create the queue
aws sqs create-queue --queue-name crm-events --region us-east-1

# Get the queue URL (save this!)
aws sqs get-queue-url --queue-name crm-events --region us-east-1
```

### Option B: Using AWS Console
1. Go to https://console.aws.amazon.com/sqs/
2. Click **"Create queue"**
3. **Type:** Standard
4. **Name:** `crm-events`
5. **Configuration:** (keep defaults)
   - Visibility timeout: 30 seconds
   - Message retention: 4 days
   - Delivery delay: 0 seconds
6. Click **"Create queue"**
7. **Copy the Queue URL** (looks like: `https://sqs.us-east-1.amazonaws.com/123456789012/crm-events`)

---

## Step 6: Create S3 Bucket

### Option A: Using AWS CLI (Recommended)
```bash
# Create bucket (name must be globally unique)
aws s3 mb s3://crm-events-archive-YOUR-INITIALS-$(date +%s) --region us-east-1

# List buckets to verify
aws s3 ls

# Test upload
echo "test" > test.txt
aws s3 cp test.txt s3://YOUR-BUCKET-NAME/test.txt
```

### Option B: Using AWS Console
1. Go to https://console.aws.amazon.com/s3/
2. Click **"Create bucket"**
3. **Bucket name:** `crm-events-archive-jw-20251222` (must be globally unique)
4. **Region:** `us-east-1`
5. **Block Public Access:** Keep all checkboxes CHECKED (security)
6. **Bucket Versioning:** Disabled (optional: enable for safety)
7. **Encryption:** Enable (recommended)
8. Click **"Create bucket"**

---

## Step 7: Update Your .env File

Edit `consulting-crm-analytics/.env`:

```env
# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=AKIA******************  # Your access key
AWS_SECRET_ACCESS_KEY=************************  # Your secret key
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789012/crm-events
S3_BUCKET_NAME=crm-events-archive-jw-20251222
```

---

## Step 8: Test the Integration

### 8.1 Test SQS Connection
```bash
cd /c/Users/jesse/consulting-crm-analytics
source venv/Scripts/activate

python -c "
import boto3
import os
from dotenv import load_dotenv

load_dotenv()

sqs = boto3.client('sqs', region_name=os.getenv('AWS_REGION'))
response = sqs.send_message(
    QueueUrl=os.getenv('SQS_QUEUE_URL'),
    MessageBody='Test message from Django'
)
print(f'✅ Message sent! Message ID: {response[\"MessageId\"]}'
"
```

### 8.2 Test S3 Connection
```bash
python -c "
import boto3
import os
from dotenv import load_dotenv

load_dotenv()

s3 = boto3.client('s3', region_name=os.getenv('AWS_REGION'))
s3.put_object(
    Bucket=os.getenv('S3_BUCKET_NAME'),
    Key='test/test.txt',
    Body=b'Hello from Django'
)
print('✅ File uploaded to S3!')
"
```

### 8.3 Verify in AWS Console

**SQS:**
1. Go to https://console.aws.amazon.com/sqs/
2. Click on `crm-events` queue
3. Click **"Send and receive messages"**
4. Click **"Poll for messages"**
5. You should see your test message

**S3:**
1. Go to https://console.aws.amazon.com/s3/
2. Click on your bucket
3. Navigate to `test/test.txt`
4. Click on it to download or view

---

## Step 9: Test Full Event Flow

### 9.1 Start your services
```bash
# Terminal 1: Django
python manage.py runserver

# Terminal 2: Celery Worker
celery -A analytics worker --loglevel=info

# Terminal 3: Celery Beat
celery -A analytics beat --loglevel=info
```

### 9.2 Insert test data in CRM
```sql
-- Connect to your Supabase DB
INSERT INTO leads (company_name, email, lead_status, estimated_value)
VALUES ('AWS Test Corp', 'aws-test@example.com', 'qualified', 100000);
```

### 9.3 Watch the logs
In Terminal 2 (Celery Worker), you should see:
```
[INFO] Found 1 unprocessed events
[INFO] Published 1 events to SQS
[INFO] Marked 1 events as processed
[INFO] Processing event: INSERT_LEADS for leads:...
[INFO] Archived event to S3: events/2025/12/22/leads/...
```

### 9.4 Verify in AWS
- **SQS:** Queue should show messages sent (CloudWatch metrics)
- **S3:** Check `events/2025/12/22/leads/` folder for archived events

---

## Cost Estimates (Conservative)

**Assumptions:**
- 1,000 CRM events/day
- 30,000 events/month

**Monthly Costs:**
- SQS: $0.00 (well within 1M free tier)
- S3 Storage: ~$0.01 (for ~1GB of JSON events)
- S3 Requests: $0.00 (within free tier)
- **Total: ~$0.01/month** 🎉

**Note:** EC2/ECS costs would be extra if you deploy there (t3.micro = ~$7/month, or use free tier for 12 months)

---

## Security Best Practices

✅ **Done:**
- Using IAM user (not root)
- S3 bucket is private
- Access keys not in code (using .env)

🔒 **Additional (Optional):**
- Enable MFA on AWS account
- Rotate access keys every 90 days
- Set up AWS CloudTrail for audit logs
- Add billing alerts

---

## Troubleshooting

### "Access Denied" errors
- Check IAM permissions
- Verify access keys are correct in `.env`
- Make sure region matches (`us-east-1`)

### "Queue does not exist"
- Double-check SQS_QUEUE_URL in `.env`
- Verify queue exists: `aws sqs list-queues`

### "Bucket not found"
- Verify bucket name in `.env`
- Check bucket exists: `aws s3 ls`

### boto3 import errors
```bash
pip install boto3
```

---

## Next Steps After AWS Setup

1. ✅ AWS resources created and tested
2. 🔄 Run full end-to-end test
3. 📊 Set up BI dashboard (Metabase)
4. 🚀 Optional: Deploy to AWS EC2/ECS
5. 📈 Monitor with CloudWatch

---

## Quick Reference Commands

```bash
# Check AWS config
aws configure list

# List SQS queues
aws sqs list-queues

# List S3 buckets
aws s3 ls

# View SQS messages
aws sqs receive-message --queue-url YOUR_QUEUE_URL

# Check S3 bucket contents
aws s3 ls s3://YOUR_BUCKET_NAME --recursive

# Monitor Celery
celery -A analytics inspect active
```

---

**Need help? Common AWS Console URLs:**
- IAM: https://console.aws.amazon.com/iam/
- SQS: https://console.aws.amazon.com/sqs/
- S3: https://console.aws.amazon.com/s3/
- Billing: https://console.aws.amazon.com/billing/
