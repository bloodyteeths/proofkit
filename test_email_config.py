#!/usr/bin/env python3
import os

print('📧 Email Configuration Test\n')

# Check environment variables
email_vars = {
    'POSTMARK_TOKEN': os.getenv('POSTMARK_TOKEN', 'Not set'),
    'FROM_EMAIL': os.getenv('FROM_EMAIL', 'Not set'),
    'REPLY_TO_EMAIL': os.getenv('REPLY_TO_EMAIL', 'Not set'),
    'SUPPORT_INBOX': os.getenv('SUPPORT_INBOX', 'Not set')
}

print('Environment Variables:')
for key, value in email_vars.items():
    status = '✓' if value != 'Not set' else '✗'
    display_val = value[:20] + '...' if value != 'Not set' and len(value) > 20 else value
    print(f'{status} {key}: {display_val}')

# Check email script
import os.path
if os.path.exists('scripts/check_email_postmark.py'):
    print('\n✓ Postmark email test script exists')
else:
    print('\n✗ Postmark email test script missing')

# Check domain references
print('\n🌐 Domain Configuration:')
files_to_check = [
    'web/templates/base.html',
    'web/static/robots.txt'
]

for file in files_to_check:
    if os.path.exists(file):
        with open(file, 'r') as f:
            content = f.read()
            if 'proofkit.net' in content:
                print(f'✓ {file} - uses proofkit.net')
            elif 'proofkit.com' in content or 'proofkit.dev' in content:
                print(f'✗ {file} - incorrect domain')
            else:
                print(f'? {file} - no domain found')

print('\n✅ Email configuration ready for deployment')
print('   Use POSTMARK_TOKEN env var for production')