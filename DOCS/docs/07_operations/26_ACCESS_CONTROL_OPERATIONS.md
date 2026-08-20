# Access Control Operations

## V1 Human Role

Primary owner/operator.

## Service Roles

- API;
- worker;
- scheduler;
- migration;
- backup;
- agent runtime.

## Least Privilege

Examples:

- frontend has no database credentials;
- worker only has required source/model credentials;
- agent runtime has no broker credential;
- migration role separate where practical;
- paper execution has paper adapter only.

## Access Review

Review:

- active credentials;
- unused accounts;
- expired tokens;
- environment separation;
- service permissions.

## Revocation

On compromise or role change:

1. revoke token;
2. rotate dependent secret;
3. invalidate session;
4. review audit;
5. record change.
