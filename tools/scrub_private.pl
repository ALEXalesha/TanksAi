# Убирает из текста личную папку проектов (обе записи: с / и с \) вместе с разделителем
# после неё. Зовётся из publish_github.sh как perl -p; строки приходят через окружение,
# \Q...\E экранирует их целиком.
BEGIN { $fwd = $ENV{PRIVATE_DIR}; $bck = $ENV{PRIVATE_DIR_BS}; }
s/\Q$bck\E\\?//gi if length $bck;
s/\Q$fwd\E\/?//gi if length $fwd;
