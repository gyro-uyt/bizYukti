# Original images

Full-size originals of the images used in BizYukti, kept so that the project can be shared and rebuilt. The app itself uses resized copies:

| Folder here | Used in the app as | Where it shows |
|---|---|---|
| `logo/` | `frontend/public/brand/bizyukti-assistant.png` | AI assistant button and panel |
| `3d-icons/` | `frontend/public/landing/*.webp` | Landing page, resident home feature cards, smart picks |
| `categories/` | `frontend/public/categories/*.webp` | Smart picks cards and the Explore Spotlight wheel |
| `spaces/` | `backend/app/seed_photos/<type>/*.jpg` | Demo listing photos (warehouse, office, shop, land) |

`categories/restaurant-unsplash.jpg` is an Unsplash photo (photo-1552566626-52f8b828add9, free under the Unsplash License).

To regenerate the demo listing photos from `backend/app/seed_photos/`, run:

```
docker compose exec api python -m app.seed --refresh-photos
```

A fresh `docker compose up` seeds them automatically.
