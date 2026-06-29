# Profile Avatar Design

This design adds a persisted profile image field and lets players update it from the lobby profile panel.

## Goals

- Store each player's avatar image URL with the existing `player_profile` record.
- Return the avatar in profile data so the lobby can render it.
- Let the logged-in player open personal profile details from the lobby bottom user card and edit the avatar URL.
- Keep the top-left lobby control semantically clear by labeling the existing logout action as logout.

## Non-Goals

- No binary image upload, cropping, moderation, or file processing in this change.
- No public profile page or social profile browsing.
- No changes to game matching, room state, or rank settlement rules.

## Data Model

Add `avatar_url` to `player_profile`.

- Type: nullable string, length 500.
- Default: `NULL`, which means the frontend renders its default avatar placeholder.
- Startup self-healing in `backend/app/infrastructure/database/session.py` adds the column for existing development databases, matching the current rank field pattern.

The domain `PlayerProfile` entity gains an optional `avatar_url` attribute. `SQLGameRepository` maps it in `create_user_and_profile`, `get_or_create_profile`, and leaderboard/profile projections where relevant.

## API

`GET /api/game/profile/{player_id}` returns `avatar_url`.

`POST /api/game/profile/{player_id}/avatar` updates the current player's avatar.

Request body:

```json
{
  "avatar_url": "https://example.com/avatar.png"
}
```

Rules:

- The route uses the existing game auth token and `ensure_player_access`.
- `avatar_url` may be an empty string or `null` to clear the avatar.
- Non-empty values are trimmed and capped at 500 characters.
- Accepted URL forms are `http://`, `https://`, or root-relative `/static/...` / `/api/uploads/...` paths. Invalid values return `400`.
- Response returns `ok`, `player_id`, and the saved `avatar_url`.

## Frontend State

`frontend/src/stores/playerStore.ts` gains:

- `avatarUrl` state, initially restored from `localStorage`.
- `fetchProfile()` hydration from `avatar_url`.
- `setSession()` and `logout()` storage cleanup for `hmp_avatar_url`.
- `modifyAvatar(avatarUrl)` action that calls the new API and updates state.

The store keeps the existing shape and fetch conventions so `LobbyView.vue` can consume it directly.

## Lobby UI

The bottom user card remains the entry point, but `handleProfileClick()` opens a real profile modal instead of a feature notice.

The modal displays:

- Avatar preview.
- Nickname, username, player ID.
- Beans, total games, win rate, rank title, and stars.
- Avatar URL input with Save and Clear actions.

The footer avatar renders an image when `playerStore.avatarUrl` is present and falls back to the current default icon otherwise. The same rendering appears on the ready page.

The main lobby top-left button keeps its existing logout behavior but changes visible text from the current classic-mode label to an explicit logout label, with an accessible label that makes the action explicit.

## Error Handling

- Failed profile fetch keeps the existing UI state.
- Failed avatar save shows an inline modal error and does not close the modal.
- Clearing the avatar saves an empty value and immediately returns to the default placeholder.
- Broken remote image URLs fall back visually to the default placeholder by hiding the failed image.

## Tests

Backend tests:

- Repository maps `avatar_url` into `PlayerProfile`.
- Profile API returns `avatar_url`.
- Avatar update API saves and clears the field for the authenticated player.
- Avatar update API rejects another player's token and invalid URL values.

Frontend tests:

- `playerStore.fetchProfile()` stores `avatar_url`.
- `playerStore.modifyAvatar()` posts to the avatar endpoint and updates state.
- Lobby renders an explicit logout label instead of the current classic-mode label.
- Lobby profile modal opens from the bottom user card and renders the avatar preview/input.

Manual verification:

- Open `http://localhost:5173/lobby`.
- Confirm the top-left control clearly communicates logout and logs out.
- Open the profile modal from the bottom user card.
- Save a valid avatar URL, see it update in the footer card.
- Clear the avatar, see the default placeholder return.
