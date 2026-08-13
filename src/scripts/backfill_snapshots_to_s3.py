# One-off, manually-run backfill: rewrite `snapshot.url` rows that still
# point at (mostly expired) Discord CDN URLs to a stable S3-compatible URL.
#
# For every row whose URL still resolves, the image is downloaded and
# re-uploaded to S3-compatible storage, then the row is updated in place.
# Rows whose URL no longer resolves (expired/404) are left untouched and
# logged as unrecoverable.
#
# Run with:
#   poetry run python src/scripts/backfill_snapshots_to_s3.py [--dry-run]
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


from utils.setup import S3_COMPAT_ACCESS_URL, db_stats, s3compat_app  # noqa: E402
from utils.utils import get_content  # noqa: E402


async def main(dry_run):
    await db_stats.db.create_connection()

    rows = await db_stats.get_all_snapshots()

    total = 0
    already_s3 = 0
    migrated = 0
    unrecoverable = 0
    failed = 0

    for row in rows:
        total += 1
        url = row["url"]

        if S3_COMPAT_ACCESS_URL and S3_COMPAT_ACCESS_URL in url:
            already_s3 += 1
            continue

        try:
            img_bytes = await get_content(url, "bytes")
        except Exception as e:
            unrecoverable += 1
            print(
                f"[unrecoverable] {row['datetime']} (canvas {row['canvas_code']}): "
                f"{url} -> {e}"
            )
            continue

        if not dry_run:
            try:
                new_url = await s3compat_app.upload_image(
                    img_bytes,
                    custom_metadata={
                        "canvas_code": str(row["canvas_code"]),
                        "datetime": str(row["datetime"]),
                    },
                )
                await db_stats.update_snapshot_url(row["datetime"], new_url)
            except Exception as e:
                failed += 1
                print(
                    f"[failed] {row['datetime']} (canvas {row['canvas_code']}): {e}"
                )
                continue

        migrated += 1

    print("-" * 50)
    print("Backfill summary" + (" (dry run)" if dry_run else ""))
    print(f"  total:                              {total}")
    print(f"  already on S3:                      {already_s3}")
    print(
        f"  {'would migrate' if dry_run else 'migrated':<36}{migrated}"
    )
    print(f"  unrecoverable (expired/404):        {unrecoverable}")
    print(f"  failed (upload/db error):           {failed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="One-time backfill of salvageable snapshot images to S3."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print what would be migrated, without uploading or writing to the DB.",
    )
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
