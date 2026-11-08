import { API_CONNECTED, REPO_URL } from "@/lib/api";

/** Shown only on a website-only deployment, so visitors aren't left wondering why search does nothing. */
export function PreviewNotice() {
  if (API_CONNECTED) return null;
  return (
    <div role="status" className="border-b border-amber/25 bg-amber-wash">
      <p className="mx-auto max-w-6xl px-4 py-2.5 text-sm text-ink sm:px-6">
        <span className="font-medium">Preview.</span> You can look around and read how it works, but search
        isn&apos;t connected yet because the matching service isn&apos;t hosted.
        {REPO_URL && (
          <>
            {" "}The code and setup steps are{" "}
            <a href={REPO_URL} className="text-link underline" target="_blank" rel="noreferrer">on GitHub</a>.
          </>
        )}
      </p>
    </div>
  );
}
