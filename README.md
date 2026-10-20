# Secure Cloud Resume
 
My CV as a static website on AWS, live at **https://oltun.dev**, with a serverless visitor counter and an automated deployment pipeline.
 
## Contents
 
- [Live](#live)
- [Architecture](#architecture)
- [What's built so far](#whats-built-so-far)
- [Security](#security)
- [Security: AWS WAF (SQL injection testing)](#security-aws-waf-sql-injection-testing)
- [Design decisions and lessons learned](#design-decisions-and-lessons-learned)
- [Cost](#cost)
- [Roadmap](#roadmap)
## Live
 
- https://oltun.dev
- https://www.oltun.dev
## Architecture
 
There are three paths through the system: one serves the page, one powers the visitor counter, and one deploys changes.
 
### 1. Serving the page
 
```
Visitor
  |  HTTPS (TLS 1.2+)
  v
Cloudflare DNS (records set to "DNS only", traffic is not proxied)
  |
  v
Amazon CloudFront --- ACM certificate (us-east-1, DNS-validated, auto-renewing)
  |  Origin Access Control (signed requests)
  v
Private S3 bucket (eu-north-1, Block Public Access on)
```
 
### 2. Visitor counter
 
```
JavaScript on oltun.dev (once per browser session)
  |  POST /visit over HTTPS
  |  CORS allows only https://oltun.dev and https://www.oltun.dev
  v
API Gateway HTTP API (eu-north-1)
  |  route throttle: 1 request/second, burst 2
  v
Lambda function, Python (reserved concurrency: 2)
  |  IAM: dynamodb:UpdateItem on one table only
  v
DynamoDB table (provisioned 1 read / 1 write unit, auto scaling off)
```
 
### 3. Deployment (every change to `main`)
 
```
Branch --> pull request --> GitHub Actions runs scripts/check.sh
  |  ruleset on main: pull request required, "checks" must pass,
  |  no force-push, no deletion, no bypass
  v
main
  |
  v
AWS CodePipeline (watches main through a GitHub connection limited to this one repo)
  |  copies the repo to a private artifact bucket (objects expire after 7 days)
  v
AWS CodeBuild (smallest compute size, 5-minute timeout, one build at a time)
  |  1. runs scripts/check.sh again and stops if it fails
  |  2. zips and updates the Lambda function code
  |  3. uploads index.html and style.css to the site bucket (versioning on)
  |  4. invalidates the CloudFront cache
```
 
*AWS WAF was trialled in front of CloudFront and then removed (see [Security: AWS WAF](#security-aws-waf-sql-injection-testing) below), so it is not part of any of these paths today.*
 
## What's built so far
 
### Phase 1: Frontend
 
- HTML and CSS CV, previewed locally with VS Code Live Server
- Version-controlled in this repo
### Phase 2: Static hosting and HTTPS
 
- Private S3 bucket: Block Public Access on, SSE-S3 encryption, static website hosting off
- CloudFront distribution reading from S3 via Origin Access Control
- HTTP redirected to HTTPS, `index.html` as default root object
### Phase 3: Custom domain and WAF
 
- Domain `oltun.dev` registered with Cloudflare Registrar
- Free TLS certificate from AWS Certificate Manager covering `oltun.dev` and `www.oltun.dev`
- Certificate validated with DNS CNAME records in Cloudflare
- Both names attached to the CloudFront distribution as alternate domain names
- DNS records at Cloudflare point the apex and `www` at CloudFront
- AWS WAF trial: SQL injection probe counted in monitor mode, blocked in blocking mode, then decommissioned (see the [Security](#security) section)
### Phase 4: Visitor counter (serverless backend)
 
- DynamoDB table holding a single item (`id = "visitors"`) with a `visit_count` number, provisioned at 1 read and 1 write unit with auto scaling off, so capacity is fixed
- Lambda function (Python) that makes one atomic `UpdateItem` call with `ADD` to increment the count and return the new value; errors are logged server-side and the caller only sees a generic error
- Lambda execution role allows `dynamodb:UpdateItem` on that one table and nothing else
- API Gateway HTTP API with one route, `POST /visit`, throttled to 1 request per second (burst 2)
- CORS limited to `https://oltun.dev` and `https://www.oltun.dev`
- Lambda reserved concurrency of 2
- JavaScript in `index.html` calls the API once per browser session (using `sessionStorage`), writes the number with `textContent`, and hides the counter if the call fails, so the CV still loads normally
### Phase 5: CI/CD
 
- Every change to `main` goes through a pull request. A GitHub ruleset blocks direct pushes, force-pushes and branch deletion, requires the `checks` job to pass, and has no bypass list. I tested it: a direct push to `main` was rejected
- `scripts/check.sh` runs three checks: required files exist, the Lambda code parses, and no AWS access key IDs appear in the repo. The same script runs in GitHub Actions (free for public repos) and again inside the AWS build
- AWS CodePipeline watches `main` through a GitHub connection restricted to this one repository. CodeBuild runs the checks, updates the Lambda function from `backend/lambda_function.py`, uploads `index.html` and `style.css` to the site bucket, and invalidates the CloudFront cache
- The deploy publishes only those two named files and never deletes anything from the site bucket. Bucket versioning is on, and old versions expire after 30 days, so a bad deploy can also be rolled back from S3
- Two least-privilege IAM roles: the build role can write those two objects, update that one function, invalidate that one distribution, write its own logs and read the pipeline's artifacts; the pipeline role can use the one GitHub connection, use the artifact bucket and start that one build
- Cost limits: smallest build size, a 5-minute build timeout, one concurrent build, a private artifact bucket whose objects expire after 7 days
- Tested: a harmless change reached the live site in about a minute (not precisely timed). A deliberately failing check stopped the deploy: the build logs show the failure and no later command ran, and the Lambda, S3 and CloudFront timestamps were unchanged. I rolled the break back with `git revert`
## Security
 
### What's in place
 
- The S3 bucket is private; only this CloudFront distribution can read it (OAC)
- Plain HTTP requests are redirected to HTTPS, and the minimum TLS version is 1.2 (`TLSv1.2_2021` policy)
- The certificate auto-renews as long as its validation records stay in DNS
- MFA enabled on the AWS, Cloudflare and GitHub accounts (authenticator app)
- AWS WAF with SQL injection protection: deployed, tested, then decommissioned for cost (see the [Security: AWS WAF](#security-aws-waf-sql-injection-testing) section)
- The Lambda role follows least privilege: one action, one table
- No request data reaches the database: the Lambda ignores the request body and parameters and always updates the same fixed key, so there is no injection surface in the counter itself
- No AWS credentials exist in the page or the repo; the API endpoint is public by design because browser code has to know it
- No AWS credentials are stored in GitHub either: the pipeline pulls from inside AWS instead of GitHub pushing in, and `scripts/check.sh` fails the build if an AWS access key ID appears anywhere in the repository
- The GitHub connection can see only this one repository (checked in the pipeline wizard, where it was the only repository listed)
- The pipeline and the build run under two separate roles, each limited to named resources, with no wildcard actions
- Changes reach `main` only through a pull request that passes the `checks` job, and that rule applies to me too (no bypass list)
### Known limits of the counter
 
- **CORS is not access control.** It is enforced by browsers, not by the server. I tested with `curl` and a request claiming a disallowed origin still ran and incremented the count; CORS only stopped a browser from reading the reply. The throttle is the real control.
- **Throttling is best-effort.** AWS describes API Gateway throttling as a target, not a guaranteed hard cap. The Lambda concurrency cap, the fixed DynamoDB capacity and the account spend limit sit behind it.
- **The count can be inflated.** Anyone can script calls within the throttle. It is a simple visitor counter, not trustworthy analytics.
- **The API has no WAF in front of it, by decision.** An HTTP API can't take a WAF directly, and the alternatives cost money or add moving parts for a counter that ignores request data. See [why I did not put a WAF in front of the API](#why-i-did-not-put-a-waf-in-front-of-the-api).
### Known limits of the pipeline
 
- **Whoever can merge to `main` can deploy to production.** The ruleset stops accidents and enforces a routine, but a repository admin can edit or switch it off, so the real protection against account takeover is two-factor login on GitHub.
- **I approve my own changes.** The ruleset requires a pull request and a passing check but zero approvals, because I'm the only person on the repository and can't approve my own pull request. There is no second pair of eyes.
- **The checks are shallow.** They catch missing files, Python that doesn't parse, and AWS access key patterns. They don't run the Lambda, validate the HTML or CSS, or catch wrong logic. A change that builds but looks wrong goes live, and the answer to that is `git revert` plus bucket versioning, not the checks.
- **A pull request can change the checks themselves,** since `scripts/check.sh` lives in the repository. The ruleset still requires the check job to pass, but a change that weakens the script would pass its own weakened version.
- **No alert for a failed AWS deploy.** GitHub emails me when the Actions run fails, but I haven't set up a notification for the AWS pipeline, so a failed deploy there is visible only if I look.
- **The deploy isn't all-or-nothing.** The Lambda is updated before the site files, so if a later step failed, the backend could be updated and the site not. Building the Lambda first keeps the page from calling a backend that isn't ready, but it doesn't make the whole deploy atomic.
- **Every push to `main` deploys,** including a README-only change. It's harmless, since the same files are uploaded again, but it uses a build minute each time.
- **Concurrent builds are capped at one.** AWS's documentation says a build over the limit is throttled and not run. I set the limit but haven't tested what two simultaneous pushes do.
- **The GitHub Actions workflow uses a version tag, not a commit hash.** The action's maintainers could move a tag. The workflow has read-only permissions and no secrets, so the exposure is small, and pinning to a commit hash is the stricter option I haven't taken.
## Security: AWS WAF (SQL injection testing)
 
**Status: deployed, tested, and decommissioned on 16 Oct 2026 to avoid ongoing cost.** The live site at oltun.dev is currently **not** behind a WAF. AWS WAF would cost about $8/month for this static site (see the Cost subsection below).
 
### What I built
 
I attached a web ACL to the CloudFront distribution using the console's one-click protection. It created three AWS managed rule groups:
 
- `AWSManagedRulesAmazonIpReputationList`: blocks IPs on Amazon's threat-intelligence lists
- `AWSManagedRulesCommonRuleSet`: general web attacks such as XSS and local file inclusion
- `AWSManagedRulesKnownBadInputsRuleSet`: known exploit patterns
None of those is a dedicated SQL injection group, so I added a fourth by hand: `AWSManagedRulesSQLiRuleSet`.
 
### How I tested it
 
I ran the same two requests in two modes: a normal page load, and a classic SQL injection probe (`' OR '1'='1`, URL-encoded) in the query string.
 
```
curl -s -o /dev/null -w "%{http_code}\n" "https://oltun.dev/"
curl -s -o /dev/null -w "%{http_code}\n" "https://oltun.dev/?id=1%27%20OR%20%271%27%3D%271"
```
 
| Mode | Normal page | SQL injection probe |
|---|---|---|
| Monitor (Count) | 200 | 200, matched and counted by `SQLi_QUERYARGUMENTS` |
| Blocking | 200 | **403**, blocked by `SQLi_QUERYARGUMENTS` |
 
Monitor mode:
 
![Monitor mode: request matched and counted](docs/images/waf-monitor-mode-count.png)
![Terminal: 200 and 200 in monitor mode](docs/images/waf-curl-monitor.png)
 
Blocking mode:
 
![Blocking mode: request blocked by the SQLi rule](docs/images/waf-blocking-block.png)
![Terminal: 200 and 403 in blocking mode](docs/images/waf-curl-blocking.png)
 
All four rule groups, and the full sampled-requests view:
 
![Rule groups](docs/images/waf-rules-four-groups.png)
![Sampled requests](docs/images/waf-sampled-requests.png)
 
### What I learned
 
- **Monitor mode first.** It records what a rule would block without blocking it, which is the safe way to test a WAF before enforcing it.
- **The 403 alone isn't proof.** A private S3 bucket also returns 403 for missing paths, so I confirmed the block from WAF's sampled requests, which name the exact rule.
- **CloudFront manages its one-click web ACL.** My manually added SQL rule group disappeared after I saved the CloudFront security settings (probably because CloudFront re-applied its own configuration), so I re-added it in the WAF console.
- **A WAF is one layer, not a shield.** Within minutes of the WAF going live, automated scanners probed for `/wp-admin/install.php`. The WAF allowed those requests, because they match no attack rule. The site isn't WordPress, so there was nothing there to exploit.
- **Limits of my test.** I tested a single, simple, URL-encoded probe against the query string. I did not test encoding tricks or other injection points. SQL injection protection matters where input reaches a database. The visitor-counter API now exists, but it ignores request data entirely and DynamoDB isn't a SQL database, so there is little to inject into. The API is not behind a WAF: I evaluated that afterwards and decided against it (see [why I did not put a WAF in front of the API](#why-i-did-not-put-a-waf-in-front-of-the-api)).
### Cost
 
The one-click setup was estimated at $8.01/month at 10,000 requests/month (web ACL plus three rule groups plus request charges), and the extra SQL rule group adds roughly $1/month. WAF is billed hourly, at roughly a cent an hour on those figures, and it ran for about 30 minutes, so by arithmetic the trial should have cost a cent or two. That is an estimate from AWS's pricing; I have not checked it against the invoice. I decommissioned it because the monthly cost is hard to justify for a static CV. I disabled the protection in CloudFront, and verified in the WAF console that no web ACL remained.
 
### Alternatives considered
 
- **Cloudflare WAF:** free tier, but not open source, and it would put a second CDN in front of CloudFront.
- **Open-source WAF (ModSecurity or Coraza with the OWASP Core Rule Set):** needs a server in the request path, which CloudFront and S3 can't host. It could only be added as a lab or extra EC2 cost, so I haven't deployed it.

### Why I did not put a WAF in front of the API

After the trial I checked whether the visitor-counter API could be protected by a WAF too, and decided against it. The findings below come from AWS's documentation as of 20 Oct 2026; prices and plans may change.

- **An HTTP API can't take a WAF directly.** AWS's REST-vs-HTTP API comparison lists AWS WAF as supported for REST APIs and not for HTTP APIs. The options are putting CloudFront in front of the API (AWS re:Post answers suggest this; I haven't tested it) or rebuilding the API as a REST API, which costs more per request.
- **A WAF in front would not close the original URL.** HTTP APIs have no resource policies, so the API's own address would stay public and bypass the WAF unless I also added a secret-header check in a Lambda authorizer. That is extra moving parts for a counter.
- **The cost doesn't fit my hard-ceiling rule.** Pay-as-you-go WAF charges a monthly fee per web ACL plus per-rule and per-request fees, and the per-request fees grow under attack. CloudFront's flat-rate Free plan is $0 with no overage charges, but AWS lists its SQL database protections from the Pro plan ($15/month) upward, and the Free plan allows only 5 WAF rules. I did not check whether my account is eligible for the Free plan (the docs say accounts using the AWS Free Tier are not), or whether it would allow a SQL injection rule.
- **There is little for it to protect.** The Lambda ignores the request body and parameters, always updates one fixed key, and DynamoDB is not a SQL database. The existing limits (1 request/second route throttle, Lambda concurrency cap of 2, fixed 1 read / 1 write unit, $20/month spend limit) already bound the damage from abuse.

**Decision:** no WAF in front of the API. I would revisit this if the API ever accepts or stores user input.

## Design decisions and lessons learned
 
### Hosting, domain and API
 
- **Cloudflare DNS instead of Route 53.** Cloudflare Registrar requires Cloudflare's nameservers, so the domain can't use a Route 53 hosted zone without transferring out. The DNS records are "DNS only" so requests go straight to CloudFront and AWS stays the delivery layer.
- **Regions.** My AWS resources live in `eu-north-1`, the Region assigned to my account. CloudFront needs its certificate in `us-east-1`, and the CloudFront domain setup created the ACM certificate there for me.
- **HTTP API instead of REST API.** HTTP APIs cost less per request and include built-in CORS and route-level throttling, which is all this counter needs.
### The visitor counter and its limits
 
- **Fixed capacity instead of autoscaling.** I wanted a hard ceiling on cost. With provisioned capacity and auto scaling off, DynamoDB can't scale itself up under heavy traffic; excess requests are throttled instead of billed.
- **One atomic write.** A single `UpdateItem` with `ADD` increments and returns the count in one call, so two simultaneous visitors can't both read the same number and overwrite each other.
- **POST, not GET.** The route changes data, so it uses POST. That also stops crawlers from bumping the count with plain GET requests.
- **Once per session.** The page remembers the count in `sessionStorage`, so refreshes don't inflate the number or spend write capacity.
- **Staged limits.** The cost and abuse limits are layered (route throttle, Lambda concurrency cap, fixed DynamoDB capacity, account spend limit) so that no single control is the only thing standing between a traffic flood and the bill.
### CI/CD
 
- **Keyless GitHub-to-AWS deployment was blocked, so the pipeline pulls instead.** My plan was GitHub Actions authenticating to AWS with OIDC, which needs no stored AWS keys. In my account, listing and creating an OIDC identity provider were both refused with an explicit deny from a service control policy at the organization level, which I can't see or change. My reading is that this account type is created inside an AWS-managed organization; I haven't confirmed that from AWS's own documentation. I considered three alternatives:
  - *Activating advanced features*, which might have let me edit that policy. The activation page said it can't be reversed and removes the spend limits, and I wanted to keep the $20 limit, so I didn't. I also don't know whether it would have lifted this particular deny.
  - *Long-lived AWS keys stored as GitHub secrets.* This is the thing OIDC exists to avoid, and I chose not to.
  - *A pull-based pipeline.* AWS CodePipeline watches the repository through a GitHub connection, and CodeBuild does the deploying with a role inside the account. This is what I built. GitHub holds no AWS credentials at all, and the only thing AWS holds is a connection limited to one public repository.
- **"Available" didn't mean the GitHub connection worked.** My first connection showed Available but the app wasn't installed on my GitHub account, so the connection couldn't see any repository. The real test was the repository dropdown in the new-pipeline wizard, which came up empty. I deleted both connections, revoked the old GitHub authorization and recreated the connection with the app installed on only this repository. I found out afterwards that GitHub lists "authorized" and "installed" apps on separate pages, and only the installed one carries the repository choice. The console page for creating a connection also hung once, so I created the connection from the command line and finished it in the console.
- **Test the gate, don't just build it.** A green pipeline doesn't prove the checks work. I pushed a change that makes the check script fail, and confirmed from the build logs that it stopped at the first failing command and that no later command ran. The Lambda, S3 and CloudFront timestamps hadn't changed either. I then undid it with `git revert`, which adds a new commit and keeps the history intact, instead of rewriting history.
- **Publish by allow-list.** The build uploads only `index.html` and `style.css`. Nothing else in the repository (this README, `backend/`, `docs/`, the pipeline files) can reach the public bucket by accident, and the sync never deletes. New public files have to be added deliberately.
- **Split the roles.** The pipeline's role can use the GitHub connection and start the build but can't touch the site. The build's role can update the site and the function but can't talk to GitHub. Each is limited to the exact resources it needs, with no wildcards on actions.
- **Created the supporting pieces myself.** I created the artifact bucket (private, encrypted, objects expire after 7 days) and the build project from the command line, instead of letting the console wizard create them, so I could set the limits: a 5-minute timeout, the smallest build size, one build at a time.
- **Verified, not assumed.** Some commands I wrote came from my memory of AWS's documentation. When a command's output surprised me, such as an empty versioning status or an extra field in a lifecycle response, I checked it with a second command instead of taking it on trust.
## Cost
 
Ongoing cost is the domain (about $12/year at renewal) plus AWS usage, which I expect to be minimal for a CV site.
 
### Cost controls in place
 
- A $20/month spend limit on the AWS project, which pauses the project when reached
- A $1 AWS Budgets alert (alerts only; budgets don't set hard limits)
- Fixed DynamoDB capacity, the API throttle and the Lambda concurrency cap described above
### Pipeline costs
 
From AWS's published pricing (not yet checked against an invoice):
 
- GitHub Actions is free for standard runners on public repositories
- AWS CodePipeline: AWS's pricing page lists one free active V1 pipeline per month, and this is a single V1 pipeline
- AWS CodeBuild: the free allowance is 100 build minutes per month on the smallest compute size, which this project uses. Past that it's $0.005 per minute, and a build takes about a minute, so the free allowance covers many pushes a month
- Hard ceilings on the build: a 5-minute timeout, so one runaway build costs a few cents at most, and one concurrent build
- The artifact bucket is private, its objects expire after 7 days, and the site bucket's old versions expire after 30 days, so storage can't grow without bound
- None of these is a hard cap on spend. The $20/month project limit remains the last stop
### DynamoDB
 
The DynamoDB console estimates about $0.63/month for 1 read and 1 write unit before any free tier. AWS's pricing page lists a free tier of 25 provisioned read and write units and 25 GB per Region, so I expect this table to cost nothing. **I have not yet checked this against an actual AWS invoice.**
 
## Roadmap
 
- [x] Frontend (HTML/CSS)
- [x] Private S3 bucket and CloudFront with HTTPS
- [x] Custom domain with TLS certificate
- [x] AWS WAF with SQL injection protection: deployed, tested, decommissioned (see the [Security](#security) section)
- [x] Visitor counter (API Gateway, Lambda, DynamoDB)
- [x] CI/CD: pull request ruleset, GitHub Actions checks, and a pull-based AWS pipeline (CodePipeline and CodeBuild) that deploys the site and the Lambda from `main`
- [ ] Write-up and blog post
- [ ] Restyle the site (the counter's position is temporary, and a favicon is missing, so browsers' automatic favicon request returns a harmless 403)
- [x] Evaluated a WAF in front of the API and decided against it (see [why I did not put a WAF in front of the API](#why-i-did-not-put-a-waf-in-front-of-the-api))