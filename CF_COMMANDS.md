# Cloud Foundry Commands

## Login & Setup
cf login -a https://api.cf.ap10.hana.ondemand.com --sso
cf target -o <ORG> -s <SPACE>

## Inspect Environment
cf apps                    # List apps
cf services                # List service instances
cf routes                  # List URL routes
cf env tm-intent-classifier # View env vars

## Deploy & Manage
cf push                    # Deploy app
cf restage tm-intent-classifier  # Rebuild
cf scale tm-intent-classifier -i 2  # Scale

## Logs & Debug
cf logs tm-intent-classifier --recent
cf logs tm-intent-classifier  # Stream live
cf ssh tm-intent-classifier   # Shell access

## Cleanup
cf delete tm-intent-classifier     # Delete app
cf delete tm-intent-classifier -r  # Delete with routes
