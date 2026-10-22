# Image evals

A taste classifier learns what one person likes from example images they label
liked or disliked, and gives their agents an endpoint that scores new images
against it, with written fixes. It lives under **Reward models → Evals → New eval (image)**.

## How it works

1. **Examples.** The owner uploads liked and disliked images (PNG, JPEG, WEBP,
   GIF; HEIC is converted to JPEG). Each image is embedded once with a frozen
   SigLIP2 SO400M image model; tall images such as full-page screenshots are cut
   into up to four square tiles from the top and their embeddings averaged. The
   embedding is stored with the example, so retraining never re-embeds.
2. **Training.** `POST /api/v1/image-evals/{id}/train` fits a class-balanced L2 logistic
   head on standardized embeddings in the API process (numpy/scipy, well under a
   second for hundreds of examples). L2 strength is chosen by cross-validated
   log-loss; choosing by accuracy picks the strongest regularization on ties and
   squashes every score toward 0.5. The reported accuracy is on examples held out
   of training (leave-one-out up to 60 examples, stratified 10-fold above).
3. **Scoring.** `POST /api/v1/image-evals/{id}/score` (multipart `file`, or JSON
   `image_base64`; optional `caller`, `task`, `comments`) returns
   `{score, label, summary, fixes, keep, call_id}`. Read-only API keys may call it.
   The written fixes come from Claude (`ANTHROPIC_MODEL`), which sees four liked
   examples, close-ups of two of them, the notes the owner left when labeling
   earlier calls, the score and the image. Comments are best-effort; pass
   `comments=false` for a score only (about 1 s instead of 10–15 s).
4. **Review.** Every call is logged with its image, score and comments. The owner
   can mark a call "I like it" / "I don't" with an optional note; the call becomes
   an example (reusing its stored embedding) and its note is shown to later
   comments. The page groups calls by caller and task so a run's scores read as a
   trajectory across drafts.

Agents use `stash image-eval check <id> <image>` or the `stash_image_eval_score` MCP tool.
The server only accepts images: agents render their own HTML or SVG first. The API
never fetches URLs or renders pages.

## Running it

| Setting | Where | Meaning |
| --- | --- | --- |
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | API | Needed for `modal` mode. Today they are set on the reward worker only. |
| `IMAGE_EVAL_IMAGE_DIR` | API | Local image directory when S3 is not configured (development and tests). Production stores images in the private S3 bucket. |

Deploy the embedding function once per change to `rm_worker/taste_embed.py`:

```sh
modal deploy rm_worker/taste_embed.py
```

It runs on a T4 with a 10-minute scale-down window; the model weights are baked
into the image. The first call after an idle period waits for a cold start.

## Limits

- 1,000 examples per classifier, 100 images per upload request, 15 MB and
  60 megapixels per image.
- The held-out accuracy measures agreement with the owner's labels, not general
  quality. A classifier built only from reference images (for example, an
  artist's drawings versus generic AI drawings) tends to give every reasonable
  imitation a high score; labeling some agent output is what teaches it the
  difference between close and very close.
