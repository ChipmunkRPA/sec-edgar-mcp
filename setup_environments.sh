#!/bin/bash

echo "Setting up GitHub environments for PyPI publishing..."

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if gh CLI is authenticated
if ! gh auth status > /dev/null 2>&1; then
    echo -e "${RED}Error: GitHub CLI is not authenticated${NC}"
    echo "Run: gh auth login"
    exit 1
fi

REPO="stefanoamorelli/sec-edgar-mcp"

echo -e "${YELLOW}Creating 'pypi' environment...${NC}"
gh api -X PUT "repos/${REPO}/environments/pypi" \
  --input - <<< '{
    "deployment_branch_policy": {
      "protected_branches": false,
      "custom_branch_policies": false
    }
  }' && echo -e "${GREEN}✓ pypi environment created${NC}" || echo -e "${RED}✗ Failed to create pypi environment${NC}"

echo -e "${YELLOW}Creating 'testpypi' environment...${NC}"
gh api -X PUT "repos/${REPO}/environments/testpypi" \
  --input - <<< '{
    "deployment_branch_policy": {
      "protected_branches": false,
      "custom_branch_policies": false
    }
  }' && echo -e "${GREEN}✓ testpypi environment created${NC}" || echo -e "${RED}✗ Failed to create testpypi environment${NC}"

echo ""
echo -e "${GREEN}Environments setup complete!${NC}"
echo ""
echo "Current environments:"
gh api "repos/${REPO}/environments" --jq '.environments[].name' 2>/dev/null || echo "Unable to list environments"

echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Go to https://pypi.org/manage/account/ → Publishing"
echo "2. Add trusted publisher with:"
echo "   - Repository: ${REPO}"
echo "   - Workflow: publish_pypi.yml"
echo "   - Environment: pypi"
echo ""
echo "3. Do the same for https://test.pypi.org/ with environment: testpypi"
echo ""
echo -e "${GREEN}Then you're ready to publish!${NC}"