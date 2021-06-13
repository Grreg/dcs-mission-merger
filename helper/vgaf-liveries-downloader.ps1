# Source file location
# $source = 'http://speedtest.tele2.net/10MB.zip'
# Destination to save the file
# $destination = 'c:\temp\10MB.zip'
#Download the file
# Invoke-WebRequest -Uri $source -OutFile $destination

$liveries_listing = 'liveries-list.txt'
# TODO: change the download Base URL to match our server and not a random
$base_download_url = 'https://example.com/somefolder/liveries'

$update_liveries = Read-Host "Do you want to update VGAF Liveries? [y/N] "
# $update_liveries = 'y'
if ($update_liveries -eq 'y'){
    "Ok, updating the VGAF Liveries."
    "Downloading list from $liveries_listing ..."

    # --------- Download public available livery list ---------------
    $liveries_list = Get-Content .\"$liveries_listing"

    # --------- Find local Path to SavedGames Liveries and compare --
    # [Environment]::GetFolderPath("Resources")
    # Get-ChildItem -Path ~\"Saved Games\DCS\"

    # Create Liveries Folder if its not existent
    $liveries_dir = "~\Saved Games\DCS\Liveries"
    If(!(test-path $liveries_dir)){
        New-Item -ItemType Directory -Force -Path $liveries_dir
    }

    foreach($livery in $liveries_list){
        # All Liveries should be in a subfolder - therefore check for the
        # first part of the filename - skip Files without basefolder, they
        # wont work anyhow.
        if (!($livery -match '^#') -and $livery -match '(.*)/(.*)'){
            $acfolder = $Matches[1]
            $zipfile = $Matches[2]
            If(!(test-path "$liveries_dir\$acfolder")){
                New-Item -ItemType Directory -Force -Path "$liveries_dir\$acfolder"
            }

            if(!(test-path "$liveries_dir\$acfolder\$zipfile")){
            # Now Download and copy the file into this new folder
            # There is currently no check if the File has changed, so only new
            # skins will be downloaded, but now changes yet! In Future a Checksum
            # could be implemented to verify if something has changed.
            "Downloading: $base_download_url/$acfolder/$zipfile ---> $liveries_dir\$acfolder\$zipfile"
            Invoke-WebRequest -Uri "$base_download_url/$acfolder/$zipfile" -OutFile "$liveries_dir\$acfolder\$zipfile"

            # Unpack ZIP file otherwise DCS wont recognize it
            expand-archive -path "$liveries_dir\$acfolder\$zipfile" -destinationpath "$liveries_dir\$acfolder"
            }
        }
    }
}

