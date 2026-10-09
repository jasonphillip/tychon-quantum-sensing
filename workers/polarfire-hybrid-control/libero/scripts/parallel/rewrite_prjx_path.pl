#!/usr/bin/env perl
# rewrite_prjx_path.pl OLD_PROJECT_LOCATION_BS NEW_PROJECT_LOCATION_BS PRJX_PATH
#
# Rewrites the absolute project-self-path inside a cloned Libero prjx file.
# Both backslash and forward-slash forms of the path are replaced (Libero
# stores both variants in different KEY entries).
#
# Example:
#   perl rewrite_prjx_path.pl \
#     'C:\Microchip\Libero_SoC_2025.2\SmartHLS\SmartHLS\reference_designs\Icicle_SoC\ref_design\MPFS_ICICLE_Vectorblox' \
#     '~\libero_seedsweep\seed_7\MPFS_ICICLE_Vectorblox' \
#     ~/libero_seedsweep/seed_7/MPFS_ICICLE_Vectorblox.prjx
use strict;
use warnings;

my ($old_bs, $new_bs, $prjx) = @ARGV;
die "usage: $0 OLD_BS_PATH NEW_BS_PATH PRJX_PATH\n" unless $old_bs && $new_bs && $prjx;

(my $old_fs = $old_bs) =~ s|\\|/|g;
(my $new_fs = $new_bs) =~ s|\\|/|g;

open my $fh, '<', $prjx or die "open $prjx: $!";
local $/; my $text = <$fh>; close $fh;

my $n_bs = () = $text =~ /\Q$old_bs\E/g;
my $n_fs = () = $text =~ /\Q$old_fs\E/g;
$text =~ s/\Q$old_bs\E/$new_bs/g;
$text =~ s/\Q$old_fs\E/$new_fs/g;

open my $out, '>', $prjx or die "write $prjx: $!";
print $out $text; close $out;

print "rewrite_prjx_path: replaced $n_bs BS-paths, $n_fs FS-paths in $prjx\n";
