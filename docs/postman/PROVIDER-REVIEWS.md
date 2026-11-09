# Provider Reviews in Postman

Import these two files, then select **Kompare Provider Reviews - Local example**:

- `Kompare-Provider-Reviews.postman_collection.json`
- `Kompare-Provider-Reviews-Local.postman_environment.json`

Set `base_url` to your running API URL (default `http://localhost:8000`, no trailing slash).
Set `email` and `password` to an existing active, email-verified account. In the
**Authentication** folder, send **Login**. It saves `access_token`, which
the authenticated requests use automatically. Login again when the token expires.
No registration, email verification or refresh requests are included in this collection.

Top-level folders are **Authentication**, **User** and **Admin**. User contains public
metadata/listings, reviews, tips, comments and votes. Admin contains moderation requests.
Each request indicates whether it is public, requires a user token or requires an admin.

Set `provider_slug` to an existing provider, for example `quidax`. Review/comment/tip
creation saves the returned `review_id`, `comment_id` or `tip_id`. Initial IDs are
fictional examples; use IDs from real creation/listing responses.

## Included endpoints

| Method | Endpoint | Authentication |
| --- | --- | --- |
| GET | `/providers/reviews/tags` | Public |
| GET | `/providers/tips/categories` | Public |
| GET | `/providers/{slug}/reviews` | Public |
| GET | `/providers/{slug}/reviews/summary` | Public |
| POST | `/providers/{slug}/reviews` | Optional; authenticated and anonymous examples included |
| PATCH | `/providers/{slug}/reviews/me` | Review owner |
| DELETE | `/providers/{slug}/reviews/me` | Review owner |
| GET | `/providers/{slug}/tips` | Public |
| POST | `/providers/{slug}/tips` | Public; tips are anonymous |
| GET | `/provider-reviews/{review_id}/comments` | Public |
| POST | `/provider-reviews/{review_id}/comments` | Optional; both examples included |
| PUT | `/provider-reviews/{review_id}/vote` | Logged-in user |
| DELETE | `/provider-reviews/{review_id}/vote` | Logged-in user |
| GET | `/admin/provider-reviews` | Admin |
| PATCH | `/admin/provider-reviews/{review_id}/status` | Admin |
| DELETE | `/admin/provider-reviews/{review_id}` | Admin |
| GET | `/admin/provider-review-comments` | Admin |
| DELETE | `/admin/provider-review-comments/{comment_id}` | Admin |

Each request includes descriptions, example responses and a post-response check.
See the saved response examples on each request, including common failure cases.
Optional query parameters appear disabled in **Params**; enable the filters you need.
Pagination accepts `page >= 1` and `per_page` from 1 to 100. Multiple review tags are
sent by repeating the `tags` query parameter.

## Suggested flow

1. **Login** as the user; send **Create my review**. It saves `review_id`. The review
   starts as `pending`, so public listing/comments/voting do not expose it yet.
2. To publish it, use the same Login request with an existing `super_admin` or
   `support_admin` account. Send **Update review status** with `status: "published"`.
   The current authentication guard permits those two admin types only.
3. Return to public listing and summary. Login as the original user for owner actions
   or voting. Other users can comment or vote after logging in with their own accounts.
4. **Update my review** returns the review to pending moderation. An empty update
   returns 400. **Delete my review** hides it rather than physically removing it.
5. **Create tip** saves `tip_id`. An admin can use **Publish tip**, a convenience example
   of the same status endpoint, to publish it. Public tips include published entries only.
6. Admin comment moderation supports listing/filtering and hiding comments. New comments
   on published reviews are immediately published by the current implementation.

Authenticated users can have one review per provider; duplicates return 409. Hidden
reviews remain stored and still count toward that ownership restriction. Anonymous
reviews have no owner and cannot be edited through `/reviews/me`. The anonymous and
authenticated creation requests are alternatives, not steps that must both be sent.

`is_helpful: true` records a helpful vote; `false` records a not-helpful vote. Repeating
the PUT updates the same user's vote. DELETE removes only the current user's vote.

Review status values are `pending`, `published`, `hidden`; review types are `review`,
`tip`. Discover valid review tags and tip categories through the included metadata
requests. A tip's severity is assigned by the backend, not supplied in its payload.

Examples are illustrative and contain no real credentials. Importing the files sends
no requests. Send requests individually so that moderation and deletion are deliberate.
User, anonymous and admin examples reflect the existing API's permissions.
