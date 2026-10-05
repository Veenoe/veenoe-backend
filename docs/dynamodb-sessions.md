# VEENOE-10: session persistence

The prototype starts with an empty DynamoDB table. There is no MongoDB backfill,
fallback, dual write, or historical-data compatibility requirement. The repository
owns AWS expressions; the service owns session lifecycle rules; the API owns
authentication, validation, and HTTP error mapping.

## Model and access patterns

One DynamoDB Standard table is created in each environment:
`veenoe-dev-sessions` and `veenoe-prod-sessions`. Each session is one item:

```
pk       USER#<verified Clerk user ID>
sk       SESSION#<session ID>
data     compact JSON of the Pydantic session model
revision integer optimistic concurrency version
```

Session IDs are 53 characters: a 20-digit UTC creation timestamp
(`YYYYMMDDhhmmssffffff`), a hyphen, and a random UUID4's 32 hex digits. The server
generates the ID and `started_at` from the same instant. Clients treat IDs as opaque.
Lexicographic sort gives creation order, with random tie ordering at identical
microseconds. This avoids a lookup item, duplicated history records, transactions,
and a GSI. UUID randomness avoids same-time collisions across Lambda instances;
conditional create protects against accidental replacement.

| Access pattern | Operation and key |
| --- | --- |
| Create authenticated user's session | Conditional PutItem on owner + generated ID |
| Read own session | Strong GetItem on owner + supplied ID |
| Lifecycle, feedback, transcript, or title update | UpdateItem on owner + ID, requiring the read revision |
| Recent history | Strong Query of owner partition, `begins_with(sk, SESSION#)`, descending |
| Delete own session (existing endpoint) | DeleteItem on owner + ID, requiring the read revision |
| Cross-user access | Caller can only construct its own partition; foreign ID returns the same 404 as missing |

We evaluated two tables (sessions plus history) and one table with a random ID
plus time GSI. Both add coordination or an eventually consistent history read.
The ordered opaque ID makes a single composite-key table sufficient for the
current access patterns. There are no indexes, scans, analytics keys, or generic
workflow framework.

`data` is serialized as JSON because no request queries its interior fields.
This keeps curriculum/assessment serialization provider-independent and avoids
SDK number conversion concerns. Updates rewrite the bounded payload and advance
`revision` atomically. All mutations are conditional, including rename and delete;
a stale rename cannot erase a newer assessment, and an update cannot recreate a
deleted session. Session and history reads are strongly consistent. A history
page is not a multi-item snapshot; newly created items appear on refreshing the
first page. Expiry only reconciles sessions actually read, using conditional writes.

## Lifecycle and API integration

Existing browser-compatible names remain `in_progress`, `completed`, and
`abandoned`. Token issuance succeeds before insertion. Abandon and expiry never
overwrite completion. Expiry uses the provider's session duration plus two minutes
of delivery grace, preserving the prior business rule. Late completion reconciles
expiry first and returns 409. Duplicate completion returns the first saved result.
Concurrent writes otherwise return 409; refresh before retrying.

Session details now require authentication and ownership; browser result caches
also include the authenticated user ID and wait for auth readiness. Shared public report
URLs are no longer supported. No request accepts an owner ID. The API distinguishes
404 missing/inaccessible, 409 conditional conflict, 413 storage-size rejection,
422 request validation, 503 AWS failures, and sanitized 500 unexpected failures.
Logs contain event/error types, never raw AWS messages or transcript contents.

`GET /api/v1/viva/history?limit=20&cursor=<last-session-id>` returns `sessions`
and nullable `next_cursor`. Limits range from 1 to 50. One DynamoDB Query is made
per page; its 1 MiB response boundary may return fewer items than requested.
The cursor contains only an ID: the authenticated owner always determines its
partition. The webapp loads additional pages explicitly and applies optimistic
rename/delete changes across loaded pages. Search operates on loaded sessions.

## Transcript and size limits

Only text may be submitted as optional `transcript` on conclusion. This change
does not automatically start collecting browser transcripts. No audio, provider
token, or fixed learning-style label is persisted. Existing input metadata,
curriculum choices, timestamps, status, feedback, and optional text are stored.

Text is capped at 64 KiB of UTF-8; the complete serialized item is conservatively
capped at 256 KiB before any write, below AWS's 400 KiB item limit. Request and
repository checks both account for multibyte text. Oversize data is rejected,
never silently truncated. No S3 infrastructure is needed at this bounded scope.

Run `python scripts/measure_session_size.py`. Measurements from synthetic,
five-minute-style fixtures on 2026-10-05:

| Scenario | Transcript UTF-8 bytes | Conservative item bytes |
| --- | ---: | ---: |
| English, 750 words | 5,250 | 5,860 |
| Hindi, 750 words | 10,125 | 10,735 |
| English stress, about 2,000 words | 14,028 | 14,638 |

These fixtures are not measurements of real child conversations. The byte guards
remain authoritative regardless of language or speech rate. Capture production
size statistics without content before widening this limit or adding chunk/S3
storage. Full items count toward history read capacity even though the API emits
lightweight summaries; revisit the design if transcript-heavy history traffic grows.

## Capacity, isolation, and deployment

AWS pricing checked 2026-10-05 lists 25 provisioned RCUs and 25 WCUs in the
DynamoDB Standard free tier. We deliberately provision 5 RCUs/5 WCUs per table
(10/10 total for DEV + PROD) for the small prototype. This allocation is within
that allowance if other account usage and eligibility permit; free-tier capacity
is not a per-table grant. On-demand would simplify bursts but does not use this
provisioned-capacity allowance. Item size affects consumed capacity. SDK retries
are bounded; exhausted throttling returns 503. Increase capacity or switch billing
mode through Terraform/GitHub Actions if real traffic warrants it.

Encryption at rest uses DynamoDB's default AWS-owned key. PROD has deletion
protection. PITR, autoscaling, streams, TTL, replicas, and customer-managed KMS
keys are not enabled for this disposable prototype; paid backups need an explicit
production retention/recovery decision before reliance on durable history.

Revisit these omissions against measured needs and an agreed budget:

| Feature | When to reconsider |
| --- | --- |
| More capacity or bounded autoscaling | Sustained throttling or unacceptable request latency. Measure consumed capacity and item sizes first; budget for capacity above the account's free allowance. |
| PITR or scheduled backups | History becomes important enough that accidental deletion or corruption needs recovery. Define recovery time, recovery window, retention, and restore testing. This can matter before traffic grows. |
| Streams | A specific background consumer needs session-change events, such as downstream processing. Budget for that consumer as well. |
| Multi-region replicas | Availability or user latency requires another Region and funding covers replicated writes and duplicate storage. |
| Customer-managed KMS key | A concrete security or audit requirement needs control of encryption keys; default encryption is already enabled. |
| Secondary index | A new access pattern cannot use the owner/session keys efficiently; estimate added write capacity and storage first. |
| TTL | A business/privacy retention policy requires automatic deletion. TTL is not a backup or a substitute for session expiry; it deletes history and is not itself a paid optional feature for this single-region table. |

Keeping optional features off does not cap the AWS bill: storage beyond the free
allowance, other tables, and the existing Lambda/API Gateway/logging/state-storage
services can still incur charges. Fixed provisioned capacity prevents this table
from automatically increasing throughput spend; it does not cap storage growth.

Terraform passes each table's name directly to its Lambda. Runtime roles permit
only GetItem, PutItem, UpdateItem, Query, and DeleteItem against their exact table
ARN. DeleteItem is needed by the existing delete endpoint. Runtime roles have no
scan or table-management access. Existing separate DEV/PROD state and GitHub
environments remain intact. SSM fetches only Google and Clerk secrets, with no
MongoDB requirement. Obsolete DEV SSM resources are removed from management
without deleting operator-owned secrets (`removed` blocks, `destroy = false`).
Operators can retire those unused parameters separately; the runtime cannot read them.

The existing bootstrap deployment policies need two additional scoped read
actions, DescribeContinuousBackups and DescribeTimeToLive, because the locked AWS
provider reads those settings even without backups or TTL enabled. Apply the
bootstrap change through an authorized operator GitHub Actions workflow before
the application deployment. The app deploy roles cannot modify their own policies.
No CLI deployment is part of this change. Use Deploy Development PLAN to inspect
the real state-aware plan, then APPLY through GitHub Actions. PROD remains
restricted to master and its Production environment.

For local development, copy `.env.example` to `.env`, start DynamoDB Local,
and create `veenoe-local-sessions` with string hash key `pk` and sort key `sk`.
An explicitly configured local endpoint uses dummy signing credentials; deployed
Lambda uses its IAM role through the default AWS SDK credential chain. Do not set
`DYNAMODB_ENDPOINT_URL` on deployed Lambda.

## Verification and remaining live evidence

Automated tests use Moto to execute the real DynamoDB API expressions and
conditional writes. They cover creation, ownership, consistent reads, missing
sessions, descending history/pagination, stale updates/deletes, terminal-state
races, expiry, transcript limits, sanitization, and HTTP mappings. Moto does not
prove AWS IAM, network access, throttling timing, or deployed behavior.

Local verification on 2026-10-05: 122 backend tests passed; the 140 existing
webapp tests and two new pagination/cache-isolation regressions passed; TypeScript
and lint checks for changed frontend files passed. Terraform formatting and both
root configurations validated, and two mocked DEV/PROD plans passed. The Linux
Lambda ZIP built at approximately 29.75 MiB, with packaging checks confirming no
Motor, Beanie, PyMongo, or BSON packages. These results do not substitute for the
real state-aware plan, deployment IAM verification, or live DEV smoke.

After DEV deployment, populate development-environment secrets
`DEV_SMOKE_OWNER_TOKEN` and `DEV_SMOKE_OTHER_TOKEN` with fresh, short-lived Clerk
JWTs for two distinct synthetic test users and manually run **Smoke DEV Sessions**
on this feature branch. The workflow creates two sessions through the real DEV
API, checks own/foreign reads and writes, assessment/transcript persistence,
history/pagination, and deletion. It cleans up synthetic records and prints no
tokens or private bodies. It issues two Gemini tokens; never use real child data.
Its host guard prevents PROD calls. Save the workflow result before marking the
ticket Done. A real DEV plan and live smoke have not been run locally.

## Test the feature branch before merging

Both repositories use `Veenoe-10-dynamodb-sessions`. Local testing works with the
uncommitted changes. GitHub Actions checks out committed, pushed branch contents,
so it cannot test a workstation-only diff. When ready, the operator can commit
and push this branch without merging it; no commit, push, or deployment is made
as part of this documentation update.

### 1. Local automated checks (no AWS resources)

From PowerShell in `D:\Veenoe\veenoe-backend`, with Python 3.12 and the development
dependencies installed:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ --ignore=tests/test_packaging.py
.\.venv\Scripts\python.exe scripts/measure_session_size.py
terraform fmt -check -recursive infra
terraform -chdir=infra/app init -backend=false
terraform -chdir=infra/app validate
terraform -chdir=infra/app test
terraform -chdir=infra/bootstrap init -backend=false
terraform -chdir=infra/bootstrap validate
```

Moto tests exercise database expressions without creating AWS resources.
Terraform initialization downloads providers; mocked tests do not access real
AWS state or apply anything. Packaging checks separately require the Linux Lambda
ZIP, built with `python scripts/build_lambda.py`; the **Checks** workflow builds
that artifact before running the complete suite, including packaging tests.

From `D:\Veenoe\veenoe-webapp`, with npm dependencies installed:

```powershell
npm test
npx tsx --test tests/history-pagination.test.ts
npx tsc --noEmit
npx eslint lib/hooks/use-history.ts lib/hooks/use-viva-result.ts lib/api/history.ts components/sidebar/history-list.tsx components/sidebar/search-dialog.tsx
```

The explicit pagination test command ensures the top-level regression file is
included even when the shell's glob handling differs. Expect passing tests,
type checks, formatting, and mock plans before proceeding.

### 2. Inspect and deploy DEV from the branch using Actions

1. Ensure the bootstrap deployment-policy changes have been applied by an
   authorized operator through GitHub Actions. This repository currently has
   no bootstrap deployment workflow; its app workflow cannot grant its own IAM
   permissions. If that prerequisite is missing, live DEV deployment is blocked
   until an authorized bootstrap workflow/process is available.
2. After the operator pushes the feature branch, review its **Checks** run. Run
   frontend checks against the same branch in the webapp repository.
3. Ensure the GitHub `development` environment allows deployment from this branch.
   The AWS trust policy uses that environment; GitHub's branch restrictions and
   required reviewers still apply. Do not change Production restrictions.
4. Open **Actions → Deploy Development → Run workflow**, choose
   `Veenoe-10-dynamodb-sessions`, and choose **PLAN**. Inspect the real state-aware
   plan: DEV table creation, DEV Lambda configuration, and scoped IAM changes.
   Confirm PROD resources are absent and old MongoDB parameters are detached
   without deletion. PLAN does not apply the infrastructure changes.
5. Run the same workflow on the same branch with **APPLY** after reviewing PLAN.
   APPLY generates and checks a fresh plan; inspect that run as well. It updates
   the shared DEV backend, so coordinate with other DEV users. Review its health,
   database, authentication, CORS, and post-apply zero-diff checks.

Existing manual workflows can run on a selected branch, but GitHub requires
`workflow_dispatch` registration on the default branch. The new **Smoke DEV
Sessions** workflow is feature-branch-only and may not be available for manual
dispatch before merging. Do not depend on it for pre-merge evidence. See
[GitHub's manual workflow documentation](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).

### 3. Live API smoke without merging the new workflow

After the Actions DEV deployment, run the checked-out script locally; this tests
the deployed API and does not deploy resources. Obtain fresh short-lived Clerk
JWTs for two distinct synthetic DEV users. Use an owner with no existing sessions
or concurrent activity so newest-first history assertions remain deterministic.
Populate tokens privately in the process environment; never put them in Git,
command history, screenshots, or shared logs.

```powershell
$env:DEV_API_BASE_URL = 'https://api-dev.veenoe.com'
# Set DEV_OWNER_TOKEN and DEV_OTHER_TOKEN privately before running.
.\.venv\Scripts\python.exe scripts/smoke_dev_sessions.py
Remove-Item Env:DEV_OWNER_TOKEN, Env:DEV_OTHER_TOKEN -ErrorAction SilentlyContinue
```

Success prints the smoke summary and removes the two synthetic records. The script
verifies create, own/foreign reads, foreign rename rejection, rename, assessment
and transcript persistence, history pagination, abandon, and deletion. It requests
two Gemini tokens, so it is not an entirely offline or guaranteed-free check.
On failure, inspect the sanitized failure, refresh expired tokens if needed, and
verify cleanup; failed cleanup can leave synthetic records. Save the run result.

### 4. Exercise the browser against DEV with a local backend

Once the DEV table exists, a local backend can use it without redeploying on every
edit. In the backend `.env`, set `DYNAMODB_TABLE_NAME=veenoe-dev-sessions` and
`AWS_REGION=ap-south-1`, supply DEV Google/Clerk configuration, and remove
`DYNAMODB_ENDPOINT_URL`. Authenticate locally using an approved AWS profile with
only the documented DEV table data-plane permissions; local code does not inherit
the deployed Lambda role. Keep `.env` and credentials out of Git.

```powershell
# In D:\Veenoe\veenoe-backend; AWS_PROFILE identifies your authorized DEV profile.
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8080
```

In the webapp `.env.local`, set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8080`
and use the corresponding DEV Clerk configuration. Restart `npm run dev` after
changing environment variables. Backend CORS must allow the actual local frontend
origin. This path needs internet and writes real shared DEV data.

Manually start and complete a synthetic session, refresh its result, rename it,
load older history pages (create more than 20 sessions if testing the browser's
page boundary), and delete it. Switch accounts and confirm the other user cannot
see its history or result URL. Sign out and verify private results are unavailable.
Repeat with the local frontend pointing directly at `https://api-dev.veenoe.com`
to exercise the deployed backend. Remove synthetic sessions after testing.

Do not mark the ticket Done solely on mock tests: retain the real DEV plan,
successful Actions deployment, live ownership/persistence smoke, and browser
verification evidence. No master merge or PROD deployment is required for these
DEV checks.

## Official references

- [AWS access-pattern-driven modeling](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/data-modeling.html)
- [AWS read consistency](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html)
- [AWS conditional expressions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.ConditionExpressions.html)
- [AWS item and Query limits](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Constraints.html)
- [AWS current pricing](https://aws.amazon.com/dynamodb/pricing/)
- [Terraform DynamoDB table](https://registry.terraform.io/providers/hashicorp/aws/5.100.0/docs/resources/dynamodb_table)
- [Locked provider's table implementation](https://github.com/hashicorp/terraform-provider-aws/blob/v5.100.0/internal/service/dynamodb/table.go)
- [Terraform resource removal](https://developer.hashicorp.com/terraform/language/resources/syntax#removing-resources)
