#!/bin/bash

# Fix all domain references to proofkit.net
echo "Updating all domain references to proofkit.net..."

# List of files to update
files=(
    "web/static/robots.txt"
    "web/templates/status.html"
    "web/templates/base.html"
    "web/templates/industries/autoclave.html"
    "web/templates/industries/concrete.html"
    "web/templates/industries/coldchain.html"
    "web/templates/industries/powder.html"
    "web/templates/industries/sterile.html"
    "web/templates/industry/haccp.html"
    "web/templates/legal/terms.html"
    "web/templates/legal/imprint.html"
    "web/templates/legal/privacy.html"
)

# Update each file
for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo "Updating $file..."
        # Replace proofkit.com with proofkit.net
        sed -i '' 's/proofkit\.com/proofkit.net/g' "$file"
        # Replace proofkit.dev with proofkit.net
        sed -i '' 's/proofkit\.dev/proofkit.net/g' "$file"
        # Update email addresses
        sed -i '' 's/@proofkit\.com/@proofkit.net/g' "$file"
        sed -i '' 's/@proofkit\.dev/@proofkit.net/g' "$file"
    fi
done

echo "Domain update complete!"