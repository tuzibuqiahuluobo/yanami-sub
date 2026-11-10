/** Native WebView paths only; browser File.name cannot identify a local file. */
export function nativeDropPaths(event: Event): string[] {
  const detail = (event as CustomEvent<{ path?: unknown; paths?: unknown }>).detail;
  const paths = Array.isArray(detail?.paths) ? detail.paths : [detail?.path];
  const seen = new Set<string>();
  return paths.filter((path): path is string => {
    if (typeof path !== "string" || !path.trim() || path.includes("\0")) return false;
    const key = path.toLocaleLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
