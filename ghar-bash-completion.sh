#!/bin/bash
#
# Copyright (C) 2011 Graham Forest <vitaminmoo@wza.us>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.
#
# Usage: source this file in your .bashrc, or move it to /etc/bash_completion.d/

function _ghar {
    local cur opts exclude
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    top="${COMP_WORDS[1]}"

    if [ $COMP_CWORD -eq 1 ]; then
        opts="status pull list add install uninstall"
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
        return 0
    fi

    case "$top" in

        status|pull|install|uninstall) # one or more repos

            # only present --status right after top level install command
            if [ "$top" = "install" -a $COMP_CWORD -eq 2 ]; then
                opts="--status"
            fi

            # don't offer the same repo again
            exclude="`echo ${COMP_WORDS[*]} | sed 's/ /\|/g'`"
            opts="$opts `ghar list | egrep -w -v \"$exclude\" | xargs`"

            COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
            return 0
            ;;

        list) # nothing

            return 0
            ;;

        add) # git clone arguments

            # hijack git completion for clone args support
            [[ $cur == --* ]] && _git_clone && return 0
            _filedir
            return 0
            ;;

    esac
}
complete -F _ghar ghar
