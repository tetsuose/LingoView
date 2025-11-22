import asyncio
from pathlib import Path
from rich.console import Console

console = Console()

async def convert_video_to_mp4(input_path: Path, output_path: Path) -> bool:
    """
    Convert video to browser-compatible MP4 (H.264/AAC) using ffmpeg.
    Returns True if successful, False otherwise.
    """
    try:
        # Use -y to overwrite output if exists
        # -c:v libx264: Ensure H.264 video
        # -preset fast: Faster encoding
        # -c:a aac: Ensure AAC audio
        # -movflags +faststart: Optimize for web streaming
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(input_path),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-movflags", "+faststart",
            str(output_path)
        ]
        
        console.log(f"[cyan]Converting video to MP4:[/cyan] {input_path} -> {output_path}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            console.log(f"[red]Video conversion failed:[/red] {stderr.decode()}")
            return False
            
        console.log(f"[green]Video conversion successful:[/green] {output_path}")
        return True
        
    except Exception as e:
        console.log(f"[red]Error during video conversion:[/red] {e}")
        return False
