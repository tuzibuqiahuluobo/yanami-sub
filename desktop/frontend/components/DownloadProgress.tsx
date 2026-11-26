import { formatBytes } from "@/lib/formatters";


interface DownloadProgressProps {
  name: string;
  downloaded?: number;
  total?: number;
  bytesPerSecond?: number;
}


export function DownloadProgress({
  name,
  downloaded,
  total,
  bytesPerSecond,
}: DownloadProgressProps) {
  const numericPercent =
    total && total > 0 && downloaded !== undefined && Number.isFinite(downloaded)
      ? Math.max(0, Math.min(100, (downloaded / total) * 100)) : 0;
  const shownPercent = Math.floor(numericPercent);
  return (
    <div className="download-progress">
      <div className="progress-copy">
        <strong>{name}</strong>
        <span>
          {formatBytes(downloaded)} / {formatBytes(total)}
          {bytesPerSecond ? ` · ${formatBytes(bytesPerSecond)}/s` : ""}
        </span>
        <b>{shownPercent}%</b>
      </div>
      <div className="progress-track" role="progressbar" aria-label={name}
        aria-valuemin={0} aria-valuemax={100} aria-valuenow={shownPercent}>
        <span style={{ width: `${numericPercent}%` }} />
      </div>
    </div>
  );
}
