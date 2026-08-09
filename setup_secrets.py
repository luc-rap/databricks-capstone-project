"""
One-time setup script: creates Databricks secret scopes and stores API keys.

Run this locally (with the Databricks CLI configured) or from a notebook.
Never commit the resulting secret values anywhere.

Usage:
    python setup_secrets.py
"""
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import workspace
import getpass

w = WorkspaceClient()

# Create Adzuna secret scope and store credentials
print("Setting up Adzuna API credentials...")
print("Get your credentials from: https://developer.adzuna.com/")

# Uncomment to create scope first time
# w.secrets.create_scope(scope="adzuna")

# w.secrets.put_secret(
#     scope="adzuna",
#     key="app-id",
#     string_value=getpass.getpass("Paste your Adzuna App ID: ")
# )

# w.secrets.put_secret(
#     scope="adzuna",
#     key="app-key",
#     string_value=getpass.getpass("Paste your Adzuna App Key: ")
# )

# Create Lakebase secret scope
# Uncomment to create scope first time
# w.secrets.create_scope(scope="database")
w.secrets.put_secret(
     scope="database",
     key="lakebase-url",
     string_value=getpass.getpass("Paste your Lakebase URL: ")
 )

# Grant users permission to read secrets
w.secrets.put_acl(
    scope="adzuna",
    principal="users",
    permission=workspace.AclPermission.READ,
)

w.secrets.put_acl(
    scope="database",
    principal="users",
    permission=workspace.AclPermission.READ,
)

print("✅ Secrets configured successfully!")
