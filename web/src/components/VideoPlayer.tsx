import { type ReactElement, type RefObject } from 'react';

interface VideoPlayerProps {
    videoRef: RefObject<HTMLVideoElement | null>;
    videoSrc: string | null;
}

export function VideoPlayer({ videoRef, videoSrc }: VideoPlayerProps): ReactElement {
    return (
        <section className="app__player-section">
            {videoSrc ? (
                <video ref={videoRef} className="video-player" controls src={videoSrc} />
            ) : (
                <p className="video-placeholder">请选择文件并生成字幕后开始播放</p>
            )}
        </section>
    );
}
