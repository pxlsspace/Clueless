#!/bin/bash
CANVAS_MAX=$1
TARGET_PATH=$2

if [ -z "$CANVAS_MAX" ]; then
    echo "Usage: $0 <max_canvas_code> <target_path>" && exit 1
fi

if [ -z "$TARGET_PATH" ]; then
    echo "Usage: $0 <max_canvas_code> <target_path>"&& exit 1
fi

echo "Creating temporary download folder in $TARGET_PATH/tmp"
mkdir -p $TARGET_PATH/tmp

# Loop over i = 1 to $CANVAS_MAX
for ((i=1; i<=$CANVAS_MAX; i++))
do
    # Check if the file without 'a' suffix exists
    if wget -q --spider https://pxls.space/extra/logs/dl/pixels_c${i}.sanit.log.tar.xz 2>/dev/null; then
        echo "Downloading pixels_c${i}.sanit.log.tar.xz..."
        wget -q -O $TARGET_PATH/tmp/pixels_c${i}.sanit.log.tar.xz https://pxls.space/extra/logs/dl/pixels_c${i}.sanit.log.tar.xz

        # Check if the downloaded file exists
        if [[ -f "$TARGET_PATH/tmp/pixels_c${i}.sanit.log.tar.xz" ]]; then
            echo "Extracting and moving pixels_c${i}.sanit.log.tar.xz to $TARGET_PATH/$i/..."
            tar -xvf $TARGET_PATH/tmp/pixels_c${i}.sanit.log.tar.xz -C $TARGET_PATH/$i/

            # Clean up the downloaded tar.xz file
            rm $TARGET_PATH/tmp/pixels_c${i}.sanit.log.tar.xz
        else
            echo "Error: Downloaded file pixels_c${i}.sanit.log.tar.xz not found."
        fi
    else
        echo "File pixels_c${i}.sanit.log.tar.xz does not exist."
    fi

    # Check if the file with 'a' suffix exists
    if wget -q --spider https://pxls.space/extra/logs/dl/pixels_c${i}a.sanit.log.tar.xz 2>/dev/null; then
        echo "Downloading pixels_c${i}a.sanit.log.tar.xz..."
        wget -q -O $TARGET_PATH/tmp/pixels_c${i}a.sanit.log.tar.xz https://pxls.space/extra/logs/dl/pixels_c${i}a.sanit.log.tar.xz

        # Check if the downloaded file exists
        if [[ -f "$TARGET_PATH/tmp/pixels_c${i}a.sanit.log.tar.xz" ]]; then
            echo "Extracting and moving pixels_c${i}a.sanit.log.tar.xz to $TARGET_PATH/$i/..."
            tar -xvf $TARGET_PATH/tmp/pixels_c${i}a.sanit.log.tar.xz -C $TARGET_PATH/$i/

            # Clean up the downloaded tar.xz file
            rm $TARGET_PATH/tmp/pixels_c${i}a.sanit.log.tar.xz
        else
            echo "Error: Downloaded file pixels_c${i}a.sanit.log.tar.xz not found."
        fi
    else
        echo "File pixels_c${i}a.sanit.log.tar.xz does not exist."
    fi
done

rm -r $TARGET_PATH/tmp
echo "Removed temporary download folder in $TARGET_PATH/tmp"