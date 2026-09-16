# tgctl forward protocol — native photo / album forwarding

Status: **v0.3.3 Candidate protocol**. This document describes the LoveAV-embedded TG Exporter only. It does not change or publish the historical standalone repository.

## Command compatibility

The existing CLI remains unchanged:

```powershell
tgctl forward --from <source-ref> --to <destination-ref> --ids 101 102 --dry-run --json
tgctl forward --from <source-ref> --to <destination-ref> --ids 101 102 --json
```

`--allow-large-batch` keeps the existing 20 / 200 safety boundary. Album completion is included in the effective planned count, so an automatically completed album may make a request exceed the default 20-message limit; in that case the command fails before the write and tells the caller to opt into the large batch explicitly.

## Native forwarding invariant

Forwardable content is sent only with Telethon/Telegram `forward_messages` and `from_peer=<source>`.

The forward path MUST NOT:

- call `download_media`;
- create a local photo or temporary media file;
- call `send_message` to reconstruct a photo/caption;
- copy a caption/entities into a new message;
- bypass Telegram protected-content restrictions by downloading and re-uploading.

Because Telegram performs the forward, the original photo, caption, caption entities and native forward semantics are preserved by Telegram rather than reconstructed locally.

## Supported message units

A forward unit is either:

1. one existing text/web-preview message; or
2. one standalone Telegram photo; or
3. one complete Telegram photo album identified by a single `grouped_id`.

If any explicitly requested message belongs to a photo album, the planner performs a bounded neighboring-ID scan and expands the unit to the complete observed `grouped_id` album. Album member IDs are sorted in source order and kept contiguous. A grouped unit is never split between Telegram forward batches.

If the bounded scan cannot prove the album is complete, the album is excluded with `ALBUM_INCOMPLETE`; it is never partially forwarded.

Multiple albums and standalone messages can be forwarded in one request. Unit order follows the first requested occurrence; members inside each album remain in source order.

## Protected and unsupported content

Per-message machine-readable exclusion codes include:

```text
MESSAGE_NOT_FOUND
CONTENT_PROTECTED
SERVICE_MESSAGE
UNSUPPORTED_MESSAGE
ALBUM_INCOMPLETE
```

When the source entity has Telegram `noforwards` / protected content enabled, every requested ID is returned as `CONTENT_PROTECTED` and no forward write is attempted.

If one member of a discovered album is protected, a service message or otherwise unsupported, the whole album is excluded so that TG Exporter never emits a partial album.

## Dry-run result

Dry-run performs read-only planning and never calls Telegram `forward_messages`.

The result keeps the historical fields and adds:

```text
requested_ids
successful_ids          # dry-run: planned forwardable source IDs
failed_ids
dry_run
requested_count
forwardable_count
photo_count
album_count
planned_ids             # after complete-album expansion
expanded_ids            # album members added by the planner
failures[]               # {message_id, code, reason, grouped_id?}
albums[]                 # {grouped_id, message_ids[]}
target_message_ids       # empty in dry-run
forwarded[]              # empty in dry-run
```

No message body, caption, URL, filename, credentials or private chat identifier is added to ordinary forward logs. Forward logs contain aggregate counts only.

## Real forward result

A successful real forward additionally returns:

```text
target_message_ids[]
forwarded[] = {
  source_message_id,
  target_message_id,
  grouped_id?
}
```

The result is accepted as confirmed only when Telegram returns exactly one valid target message ID for each source message in the submitted native-forward batch.

If the request may have reached Telegram but the client cannot confirm the complete target result, TG Exporter raises `WRITE_OUTCOME_UNKNOWN`. The IPC layer also maps an after-send transport break to `WRITE_OUTCOME_UNKNOWN`. Neither layer automatically retries a write with unknown outcome.

`FloodWait` propagates as the existing structured `FLOOD_WAIT` response and is not retried automatically.

## Reconciliation without forward.capture

`forward.capture` is not introduced by this Candidate. Generic reconciliation is still possible without any LoveAV/PikPak-specific logic:

1. execute `tgctl forward` and record `target_message_ids` / `forwarded`;
2. call `tgctl messages get --chat <destination-ref> --ids <target_message_ids...> --json`;
3. use the returned destination message IDs and `forward_origin` to verify the native-forward relationship;
4. any bot reply that arrives later can be read with the existing bounded history/search APIs using the caller's own before/after boundary.

No product, bot, group name, success phrase or business rule is hard-coded in TG Exporter.

## Advertised capabilities

`tgctl status --json` / `system.hello` advertise these generic capabilities when this implementation is active:

```text
forward.photos
forward.albums.atomic
forward.target_message_ids
```

There is intentionally no `forward.capture` capability until a real subscribe-before-write capture implementation exists and is independently tested.
