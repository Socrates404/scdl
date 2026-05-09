# Commands

```python

python -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pipx install scdl
pipx upgrade scdl

```



# Download one playlist
scdl -l https://soundcloud.com/pandadub/sets/the-lost-ship

# Download only new tracks from a playlist
scdl -l https://soundcloud.com/pandadub/sets/the-lost-ship --download-archive archive.txt -c

# Sync playlist
scdl -l https://soundcloud.com/pandadub/sets/the-lost-ship --sync archive.txt



## Options:
```
-l [url]                        URL can be track/playlist/user
-a                              Download all tracks of user (including reposts)
-t                              Download all uploads of a user (no reposts)
-p                              Download all playlists of a user
--force-metadata                This will set metadata on already downloaded track
-o [offset]                     Start downloading a playlist from the [offset]th track (starting with 1)


### Authentication

* Find your OAuth token by visiting SoundCloud after logging in and opening developer console (press F12) and going to the Storage tab. Then under cookies > soundcloud.com you can find the entry called oauth_token
* Place OAuth token in the config file (see below)
* You need to have this set to be able to use the `me` option
* You need to have this set to download original files (which may be lossless) if they are available
* If you have a GO+ account it will allow you to download some songs in 256 kbps AAC quality, and songs which are only available with GO+


### Config file locations
* Windows: `C:\Users\username\.config\scdl\scdl.cfg`
* Mac/Linux: `~/.config/scdl/scdl.cfg`
* If `XDG_CONFIG_HOME` is set: `$XDG_CONFIG_HOME/scdl/scdl.cfg`

#### Your `scdl.cfg` should look at least like this:
```scdl.cfg
[DEFAULT]
oauth_token=XXXXXXXXXXX
```