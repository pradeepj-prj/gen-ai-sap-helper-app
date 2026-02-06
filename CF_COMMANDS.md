# Cloud Foundry Commands

## Login & Setup
cf login -a https://api.cf.ap10.hana.ondemand.com --sso
cf target -o <ORG> -s <SPACE>

## Inspect Environment
cf apps                    # List apps
cf services                # List service instances
cf routes                  # List URL routes
cf env sap-ai-doc-assistant # View env vars

## Deploy & Manage
cf push                    # Deploy app
cf restage sap-ai-doc-assistant  # Rebuild
cf scale sap-ai-doc-assistant -i 2  # Scale

## Logs & Debug
cf logs sap-ai-doc-assistant --recent
cf logs sap-ai-doc-assistant  # Stream live
cf ssh sap-ai-doc-assistant   # Shell access

## Cleanup
cf delete sap-ai-doc-assistant     # Delete app
cf delete sap-ai-doc-assistant -r  # Delete with routes
