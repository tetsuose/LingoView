import { type ReactElement, type RefObject } from 'react';

interface VideoPlayerProps {
    videoRef: RefObject<HTMLVideoElement | null>;
    videoSrc: string | null;
}

export function VideoPlayer({ videoRef, videoSrc }: VideoPlayerProps): ReactElement {
    const handleSpeedChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
        if (videoRef.current) {
            videoRef.current.playbackRate = parseFloat(event.target.value);
        }
    };

    return (
        <section className="app__player-section">
            {videoSrc ? (
                <>
                    <video ref={videoRef} className="video-player" controls src={videoSrc} />
                    <div className="video-controls">
                        <label className="video-controls__label">
                            倍速:
                            <select className="video-controls__select" defaultValue="1" onChange={handleSpeedChange}>
                                <option value="0.5">0.5x</option>
                                <option value="0.75">0.75x</option>
                                <option value="1">1.0x</option>
                                <option value="1.25">1.25x</option>
                                <option value="1.5">1.5x</option>
                                <option value="2">2.0x</option>
                            </select>
                        </label>
                    </div>
                </>
            ) : (
                <p className="video-placeholder">请选择文件并生成字幕后开始播放</p>
            )}
        </section>
    );
}
