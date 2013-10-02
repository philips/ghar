ghar (ghar: home as repositories)
=================================

ghar can help you manage your $HOME in git using a collection of git repos
seperated by topic or privacy. For example if you work on a variety of
machines and want to share your .emacs on github but not your .ssh then ghar
is for you.

Brandon Philips <brandon@ifup.org>

INSTALL
-------

ghar aims to be self contained to make it easy to use on machines where you
may not have root. The clone of ghar you make below contains the ghar tool and
will be the directory in which you clone all of your dotfile repos.

    $ git clone git://ifup.org/philips/ghar.git
    $ export PATH=$PATH:`pwd`/ghar/bin/ # You may wish to make this permanent

If you'd like bash tab completion, either move the included
ghar-bash-completion.sh into /etc/bash\_completion.d/ (requires root),
or source the file directly:

    $ . `pwd`/ghar/ghar-bash-completion.sh

Getting Started
---------------

Now, lets create a devel repo which will contain your .vimrc config file (or
any other dotfile you choose). And then have ghar install it.

"ghar repos" are git repositories contained under the root ghar directory. For
example if you cloned ghar in a directory called $HOME/tools in the INSTALL
step above you will want to cd into $HOME/tools/ghar now to create your first
ghar repo called devel:

    $ cd ghar	# cd into the clone of ghar you made in the INSTALL step
    $ ls
    bin COPYING README
    $ mkdir devel
    $ cd devel
    $ git init
    $ mv ~/.vimrc .
    $ git add .vimrc
    $ git commit -m "vimrc: initial commit"
    $ ghar install
      devel
        installed	/home/philips/.vimrc
    $ ghar install --status
      devel
       ok	/home/philips/.vimrc

Adding External Repos
---------------------

Adding an external repo is easy. ghar will do a git clone of the external repo
into the proper directory and then install the symlinks with two commands:

    $ ghar add git://github.com/robbyrussell/oh-my-zsh.git oh-my-zsh
    $ ghar install
      oh-my-zsh
       installed	/home/philips/.oh-my-zsh

Upgrading a machine
-------------------

To upgrade a machine to the latest version of all of the repos do the
following:

    $ ghar pull		# pull in all repos
    $ ghar install	# install any new files

DONE! Enjoy the latest version of your configs.

Thanks
------
These two chaps helped me on the original bash implementation. However,
our original plan of attack ended up being too unwieldy as it used the
--git-dir directive to do the magic instead of symlinks.

- Graham Forest
- Gavin McQuillan

Contributors
------------
- Jeff Wong
- Matthew Batema
- Torne Wuff
- Jacob Kaplan-Moss
- aff0
- Charles R. Hogg III


Notes about Windows support
---------------------------

Creating symlinks under Windows requires Administrator rights. This means that
you will have to run ghar as Administrator / with elevated privileges
(Windows Vista and higher).
