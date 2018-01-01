#!/bin/bash
pkill -9 python
nohup python launch_comments.py &
nohup python launch_inbox.py &