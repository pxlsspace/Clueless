#!/bin/bash
TARGET_PATH="/home/doxy/git/pxls.space/Clueless/resources/canvases"

INFO_DATA=$(curl  -s https://pxls.space/info)
if [ $? -ne 0 ]; then
    echo "Error: Failed to retrieve data from https://pxls.space/info"
    exit 1
fi

canvasCode=$(echo "$INFO_DATA" | jq -r '.canvasCode')
if [ -z "$canvasCode" ]; then
    echo "Error: Failed to extract .canvasCode from the response"
    exit 1
fi

canvasCode=$(echo "$canvasCode" | tr -cd '[:digit:]')

download_logs() {
    canvas_id=$1
    suffix=$2

    if [[ -d "$TARGET_PATH/${canvas_id}${suffix}" ]]; then
        echo "[$canvas_id$suffix] Logs for canvas ${canvas_id}${suffix} already present, skipping."
    else
        # Check if the file exists on the server
        if curl  -s --head https://pxls.space/extra/logs/dl/pixels_c${canvas_id}${suffix}.sanit.log.tar.xz | head -n 1 | grep "200" > /dev/null; then
            echo "[$canvas_id$suffix] Downloading pixels_c${canvas_id}${suffix}.sanit.log.tar.xz..."
            # Download the file
            curl  -s -o /tmp/pixels_c${canvas_id}${suffix}.sanit.log.tar.xz https://pxls.space/extra/logs/dl/pixels_c${canvas_id}${suffix}.sanit.log.tar.xz

            # Check if the downloaded file exists
            if [[ -f "/tmp/pixels_c${canvas_id}${suffix}.sanit.log.tar.xz" ]]; then
                echo "[$canvas_id$suffix] Extracting and moving pixels_c${canvas_id}${suffix}.sanit.log.tar.xz to $TARGET_PATH/${canvas_id}${suffix}/..."
                # Unarchive and move the file
                mkdir -p "$TARGET_PATH/${canvas_id}${suffix}/"
                tar -xf /tmp/pixels_c${canvas_id}${suffix}.sanit.log.tar.xz -C "$TARGET_PATH/${canvas_id}${suffix}/"

                echo "[$canvas_id$suffix] Downloading final image for Canvas ${canvas_id} from archive"
                # Download the final image
                curl  -s -o "$TARGET_PATH/${canvas_id}/final c${canvas_id}${suffix}.png" "https://archives.pxls.space/data/images/canvas-${canvas_id}-final.png"

                # Clean up the downloaded tar.xz file
                rm /tmp/pixels_c${canvas_id}${suffix}.sanit.log.tar.xz
            else
                echo "[$canvas_id$suffix] Error: Downloaded file pixels_c${canvas_id}${suffix}.sanit.log.tar.xz not found."
            fi
        else
            echo "[$canvas_id$suffix] File pixels_c${canvas_id}${suffix}.sanit.log.tar.xz does not exist on server."
        fi
    fi
}

run_downloads() {
    for ((i=1; i<=$canvasCode; i++))
    do
        download_logs $i "" 
        download_logs $i "a"
    done
    wait
}

run_downloads