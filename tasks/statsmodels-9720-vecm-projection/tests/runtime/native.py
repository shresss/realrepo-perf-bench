"""Bounded, protected upstream regression selection. TEMPLATE: fill every Task.

Derived from the Harbor-proven pyjanitor1644 adapter; only marked blocks differ.

This supplements the parent's independent oracle. Pytest and candidate Python
execute in one child: these reports are NOT a tamper-proof adversarial oracle.
The parent owns source hashes, process limits, clock, parsing and publication.
No candidate pytest configuration, conftest, install hook or plugin is loaded.
"""

import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import sys
import time

from boundary import quiesce, strict_json
from execute import CONTEXT_ENV, THREADS, digest

# ---- Task: every value in this block is task-specific. Fill from the REFERENCE
# commit's test files; both baseline and candidate run this same protected selection.
SOURCE_COMMIT = "9a3eb9e5bcd7c5fcc438f117ae09b1da58cce77d"
# Repo-relative paths of protected assertion inputs -> sha256 of the reference bytes.
# _stage() FLATTENS them into one driver dir by basename: basenames must be unique.
PROTECTED_FILES = {'statsmodels/tsa/vector_ar/tests/test_vecm.py': 'd637873312f3977fcc6f3cfbd9c1e88fd6752c071dbc12f824013e8f42ec0bdc', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/parse_jmulti_vecm_output.py': 'c12c51194b6e667230fd3cf7a7e84b4dfc4764ba8cc27b34253f4979b95a3bfc', 'statsmodels/datasets/interest_inflation/data.py': 'ccd5eb64d92435f85bc931c5ce117e2959dc9c24566d0f3fbe817b3d68bbc539', 'statsmodels/datasets/interest_inflation/E6.csv': '458edec09a9f6b91fcc96a1b31f0b889f5f152089c1393d146b82e0ec0b41f3f', 'statsmodels/datasets/interest_inflation/E6_jmulti.csv': '8daa82f188f2193e18cc2c433cf5a3f3fe67443d47bb073c3b90f61a7c44199b', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci.txt': '5c813816649c41c3349823fe164cf7f127e3f756a806aa38f37cac33531e4158', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci_Sigmau.txt': '698254a74f08e5798c782256579526de4bf9a96d1c599774f9eb84e8b2e6621d', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci_diag.txt': 'a9c7c4027f0693fac69224e6dce7c34a5b12cd8045213e82acd2fc218c814a88', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci_fc5.txt': '7824518ed8f5ef15fda47d0b4d70b75477e3afc75feceeca26165cc408cb57c9', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci_granger_causality_dp_r.txt': 'e4c11d93d0a493fb086adedbc64a44d165e57a6da61c3140a4b45bd5e5dcb5c0', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci_granger_causality_r_dp.txt': 'f4256e448d275adfd64f4dd568f8559a74001498629ef30f1bc71c28b7b2e3ba', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci_inst_causality_dp_r.txt': '9286b50a37c05ea109bf5039eca245f4916a9b079ab3fbf73b2f88bc730389d6', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci_inst_causality_r_dp.txt': '5d30c8dee9f491db961603ed5c85c195ec7c0cb27a175314f29ffc7dbc88139c', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci_ir.txt': '6d94432cb03b8b50e6eb4bdd18db48ebf207abf25987c77498b855b003b43fcc', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci_lagorder.txt': '98d2df7f621c0b9673373962d6768f6a5c517cde147d6b52aa43f3cbd598717b', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili.txt': '0c5230e53eb4f80a1d08664f0b06cccdb111a441774c46c0685242b86cfb90ea', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili_Sigmau.txt': '1950b71cf60e8943538f01d914b7daa3a5efb910fde023084776aa96d81a805f', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili_diag.txt': '88250d7a20968a81958174e07f30d2f129c3a2c9769fe35f27c77714b8cd9908', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili_fc5.txt': '45ae25419b7cd0bf7c4f9b20c7af5056c6fa4554f901fad7678e4c79993748fc', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili_granger_causality_dp_r.txt': 'f84021dcd241cd8a59bfe2c67f660cf22ed1af9966929d5c4862aeeb0017a28c', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili_granger_causality_r_dp.txt': 'e650f528399dc81fd06906ebde92d5c110998c94d3a7cf78703f5ab41ed97fcc', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili_inst_causality_dp_r.txt': 'be57bd777967b585d2708d1e870f38a00ba9e4c93787406ccd61897c9cc1c01e', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili_inst_causality_r_dp.txt': 'df929d0cf38a1df5a780352cfb2114597dbd11e477253eca0f6b0e9e36cf7a53', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili_ir.txt': 'bb5d7700b167128b04f977667288d339de87f42bae64b35db7cf3789b0064ecb', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili_lagorder.txt': 'e059cd9b24f510db0bb14372f4b11bec554caef6f92846be7f168dc82040c720', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis.txt': '98f136c1c610ed2b35eb937f86d528a1346792df313456c455b11b658eec182a', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis_Sigmau.txt': '1f0f8d3ba6343bc64b1de66fb3769b762c212ff97d2d30f4366a9afaf18f9b96', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis_diag.txt': 'd018cbd0871a7c93bccd57f53ef2ca07b548740766d944431bb152c6a9025d7d', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis_fc5.txt': '9da119d4ee9a77be7cd567ffb0c4c1334d925e44f9fd9275d66d57c777ebaf78', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis_granger_causality_dp_r.txt': '9ba7b5b1a97124d16a01ca9921b766b8f2bf995761f7f4d5a4776df91868353d', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis_granger_causality_r_dp.txt': '1f6cea6837e5ed5aac345cb661c283b28098dfd4bc454bc32f125433342c6e00', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis_inst_causality_dp_r.txt': '87869a352b5d4e61d3800daff3cb3756286430af9f546ceb130477e8184c4e9d', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis_inst_causality_r_dp.txt': '226296c10b1431b8db676011552887e8380098b628423c330159ef6036cc3d7e', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis_ir.txt': '0cf137da97ad0151335e03a4252c614ca423ceebb129a9e24bfe7f5ab00078ea', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis_lagorder.txt': '92176870009a3e76e31defada109994ca4c7d3193e7e81d981971a80e7001eb2', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli.txt': '6e01a51e7ca7abc34239045a4704b8dfb068438ae45c3841643ea72a6d9928c9', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli_Sigmau.txt': '48de712418abc2ab3acbe18a23cbbb0d1268cdbfeacbee597acba5da28b12eec', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli_diag.txt': '19dc7d1c804799eea07991c77db2cef3c2c98c4b21697c94ae904e8218e3037b', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli_fc5.txt': '840a8cbf8bf517cfbf7b707fd70b1b79d6558c3413457dafdd407cb98e74332a', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli_granger_causality_dp_r.txt': 'ac0765b085eac88fc58078c35a91f5c72eebbdf5a90c5bc8675fb6ac558cd3ed', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli_granger_causality_r_dp.txt': '495585b2d49e178b37106449ffa4cf14068afcbaef49c1ba054c30f8f8cf7d73', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli_inst_causality_dp_r.txt': '9321271db9fead1f0fadf496df9cca5bbf033335c2d8ac42c6aa4364a3517dc6', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli_inst_causality_r_dp.txt': '39256c7fd77b9d928e973850e1ed3f9b1fa55c4ad15a0da18a513f712bcf27b6', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli_ir.txt': 'dcf27c2a3d88d7edaef58c5e339b017b7860946892908e598728ccb8b68aa283', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli_lagorder.txt': '0a9273acaaba51c525861932014b73b58a6377b48c96ca40e310e8134f0f1647', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co.txt': 'e9f745a6030cf6f36df28d23ad204220117667bca56f9ff6e7867711844502d5', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co_Sigmau.txt': '2176334cc8515203e462f2c35b18581b64c26e8f2809e65ec4e15c04092d2baa', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co_diag.txt': 'cfec6326f7d5103d090957845cc96e7d96410b025a58c63ad3179ae7f77cac82', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co_fc5.txt': 'd08d8fa47e11d04802406e24faf5cd160ffbb02e6eed90ce44c3e19dadd23fc2', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co_granger_causality_dp_r.txt': 'f22e7243fac42a9f8801fea0c0e3dddc8d5e872069f7c1d6d9129d1567a885e1', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co_granger_causality_r_dp.txt': '5d93e241c7dfd7c7c0555be5540e03d4b0d05fd49a3707c980b7638886a34527', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co_inst_causality_dp_r.txt': '2b9924e59c553b2f1f6e058d2824e6fb024384d355017be6465a2697653607c1', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co_inst_causality_r_dp.txt': 'e44817a74850ddb6722097b1120e9aacdca4ffd1f467812aa07bb9fde501e85b', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co_ir.txt': 'aa10dfd176e4dfa926a0cfd1bc91cd33c507a4088e19ad4dcb20657c1a30bb58', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co_lagorder.txt': '0fab53931bfca202a6e50015b1168569dd19f13a3be147c150f674f73eccb0e3', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo.txt': '1deccb32790864a34d47fde6a1511383bd80f3423092b1f8d402bb7f0d5609de', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo_Sigmau.txt': '63d57fcffaefc090e30cad4ec1e20271d6e1e90078f0009c49ee04af96ca7839', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo_diag.txt': 'c7d23afb8bf8c4a5af57166984a165657516d210707e6a6bd0d278e453507325', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo_fc5.txt': 'bd6f7f4fc7509dcee0bc5bcf3e4e3a86c3fe27467989e09ee6be67b23aa73180', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo_granger_causality_dp_r.txt': 'ce749edba273aa885a7aca981eade2c751e0573d96911d02b2b431c22b21449f', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo_granger_causality_r_dp.txt': '98f5995e136044e06d44fc214f2593fc75046a5ba22fbfeb9d97afce40b4513b', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo_inst_causality_dp_r.txt': 'd8a5c62cfdaac233756be95125453bd08cba7c209284d0502bacd2a86e7b788f', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo_inst_causality_r_dp.txt': '63c056fd5272afb9ae73d6fec18bc61b426775d9e3f7d6ab588db7f31fe4673d', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo_ir.txt': 'c3537e62e9a98bb511f421c80e0da8431226d2755d66febab9d57424d2f5659a', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo_lagorder.txt': '732502b261c039d19d7e7f8dd57d512c353fee8963f5c70e20de019d6b43e781', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos.txt': 'c3d830c36304caad60143227c4e4e6443efa978bf4bbd9f7888a80ae7ea6ddf3', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos_Sigmau.txt': '74ed196010d4867d7f963ce3724114d8b52f26ee4bb73bf988c1c08dc85343f8', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos_diag.txt': 'cebe61c9106c16699f2e2339bc21855e3e45497a5606e92179730311f801ed91', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos_fc5.txt': 'eb2e74a8053719d4524289d8ab7a6068a5f0184164b19d248d11205be01e9148', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos_granger_causality_dp_r.txt': '5e23aa2a5dd52a9a8f27f1aff62f85fc378fb392ba3e1f1915a18c98a931c257', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos_granger_causality_r_dp.txt': '07ed3c3fcd2b91e6c00aea5fac011f0b7f49434fe46005acd949d75733213792', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos_inst_causality_dp_r.txt': 'd79bc78b225ad3a386db5b6bdac55e137d0f3a7034e0c6e6ad9edecd752bb230', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos_inst_causality_r_dp.txt': 'f2e5ef5d4e7fd3ab62cef3861dcc0fd6103a6c6a3a32939056cbb2ffa475e88d', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos_ir.txt': 'e5c6f43f251a2b2376163901779e5243406ddd0633bd691cae4e266fcf9ac83e', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos_lagorder.txt': '599b27865bb269ad40888a63d3e07741391cf5579a2a59dcac6c2efbcfb2205a', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo.txt': 'eed81335e70594db4004a66c2ab295b8d0574307750a109095e96189ad9b6977', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo_Sigmau.txt': 'd75e584ec53df0c8d5ca064b8cf4e8c827b509bcdf4792b3269d3928619c413f', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo_diag.txt': 'ef833e980f57fb52f01a89a67d0967e4c078347f0130da0f9ee7279924eea567', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo_fc5.txt': '46c2b89ae4513d46a9b3f897906f466600b63026f47d74a659347373c21709bb', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo_granger_causality_dp_r.txt': '779a6a6c0255729d337fb2c69637fb7977882a05b27818195397443c13832736', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo_granger_causality_r_dp.txt': '3fbd55cf1c7d84f0343f2919d6b9c72196f0f66e3c3d93a24c7c0644c2403ad0', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo_inst_causality_dp_r.txt': '77a8034e26996faffd4c5c45b7861ecc9149b525071593b49e36f2e074e8ead7', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo_inst_causality_r_dp.txt': '908911318cb4bdab4efb1b3f5d0ae7e9a8dc69abc5b3a15d405e1dfbff9440aa', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo_ir.txt': '0f11b2aebd9f7ca06a32a20ee4a30325cddacbce26e0a715eacf35cbeb5b2167', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo_lagorder.txt': '42562ea18a375d024bd2c4a47e390da479de9bd257049642d7f28c343278c177', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc.txt': '9a9ba9381844f906caeb84c56fdc7102db3977cc9f73e96ba9995e9ad16a1664', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc_Sigmau.txt': 'f87ac093a0ec8d528bec3c3aed041874cc8160582047441dd3a737675ff48f70', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc_diag.txt': '34ea117d253164244819187ae7e04e803b3b723939cfb1f92da9e9cb92062fce', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc_fc5.txt': 'f05c22faffb07fc21382f8d5250a37e85898927891d1cda13fee141dff051ef6', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc_granger_causality_dp_r.txt': '466c65532e2b170eaf3a713dd475b6038d4553d26d61cce8e1ce33278c989557', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc_granger_causality_r_dp.txt': '5da59fbcc3f00152e7c487bc09e48b6e83c0eacd8c4a4c3762c2d376844679e9', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc_inst_causality_dp_r.txt': '29629d3dac02fa383d2e0b693eaad416bd1bd9048f1255225349ec42b95b3b69', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc_inst_causality_r_dp.txt': 'ae03ab820e4814a8011fabf47e7e768be8a1c89879f3f2468b88f7ce1669ee3f', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc_ir.txt': 'cff6601e78965f4041ff783af1b7ef3c578313f9a46d852d69645f4aff7c328e', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc_lagorder.txt': '749c2bde08b241fe5032c98a0450b114bff590fcfab5271b5378c6447f8a6573', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs.txt': 'b441795841d486158f1c57c8752159166a2cc1c2b36a3ea9848b484883ed2f66', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs_Sigmau.txt': '253c1d3b5f909dd20a84caa616ed46a130ad6b63ea2e40277a6852a21ae8e34e', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs_diag.txt': '074128b7dbcc6e84ddb9427e7b3c6ac61d7eac220783b56cf4722d7e7347e36a', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs_fc5.txt': 'ac15d24092d38de3011552dbc23a78b9b4bb56913939412873a10a4c794b7259', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs_granger_causality_dp_r.txt': '2c461b49044dda57f28d70c53622b3401ff4880e3c776a10276c7e80be9401e1', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs_granger_causality_r_dp.txt': 'd83fbf749f65e2e002fba7822b198827157d91bd700068be68d50aaffb22f256', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs_inst_causality_dp_r.txt': '01bdfe46f06e2a5e2a32d5a71876c64f6013fbb0558d051790cc84d31b48a119', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs_inst_causality_r_dp.txt': 'bb57263f24f29c0a9e2f8552f0703bbaebdabce9c1df630a2d3a89733dcd1615', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs_ir.txt': '68335fc7e41e9fb04e48e4983ccb9d5fcd94cdd79ac6f12593ad88e8d3740b49', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs_lagorder.txt': '5f6029b85a696289bb3bf56838e7f107023969a0777c4f2dfc071938cadd2d0c'}
TEST_FILE = "test_vecm.py"  # basename of the pytest file inside the driver dir
SELECTION = ""  # whole module; no within-file exclusions
_TEST_NAMES = ('test_ml_gamma', 'test_ml_alpha', 'test_ml_beta', 'test_ml_c', 'test_ml_det_terms_in_coint_relation', 'test_ml_sigma', 'test_var_rep', 'test_var_to_vecm', 'test_log_like', 'test_fc', 'test_granger_causality', 'test_inst_causality', 'test_impulse_response', 'test_lag_order_selection', 'test_normality', 'test_whiteness', 'test_summary', 'test_exceptions', 'test_select_coint_rank', 'test_VECM_seasonal_forecast')
EXPECTED_NODEIDS = tuple(sorted(f"{TEST_FILE}::{name}" for name in _TEST_NAMES))
EXPECTED_COUNT = len(EXPECTED_NODEIDS)  # must equal the Linux collection count exactly
# ---- end task-specific block


class NativeSourceError(ValueError):
    """A pinned verifier input is missing or differs from the declared bytes."""


def selection_manifest(upstream):
    """Check the protected REFERENCE inputs and return a path-independent pin.

    Both role snapshots run these same reference-source tests.
    """
    upstream = Path(upstream)
    for relative, expected in PROTECTED_FILES.items():
        path = upstream / relative
        if (not path.is_file() or path.is_symlink()
                or any(parent.is_symlink() for parent in path.parents)
                or digest(path) != expected):
            raise NativeSourceError(f"protected native input mismatch: {relative}")
    manifest = {
        "schema_version": 1, "mode": "protected_upstream",
        "source_commit": SOURCE_COMMIT, "selection": SELECTION,
        "expected_count": EXPECTED_COUNT, "nodeids": list(EXPECTED_NODEIDS),
        "files": dict(PROTECTED_FILES),
    }
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return {**manifest, "sha256": hashlib.sha256(encoded).hexdigest()}


def pytest_arguments(driver):
    """Return a fixed selection with all candidate discovery routes disabled."""
    driver = Path(driver)
    return [
        str(driver / TEST_FILE), "-q", "-k", SELECTION,
        "-c", str(driver / "pytest.ini"), f"--rootdir={driver}",
        "--noconftest", "--import-mode=importlib", "-p", "no:cacheprovider",
        "-o", "addopts=", "--color=no", "--tb=short", "--maxfail=1",
    ]


def validate_summary(value):
    """Return None only for all expected tests passing all three pytest phases."""
    required = {"schema_version", "selected", "selected_count", "deselected_count",
                "collection_errors", "exit_code", "reports", "duplicate_reports"}
    if not isinstance(value, dict) or set(value) != required:
        return "native summary schema mismatch"
    for key in ("schema_version", "selected_count", "deselected_count",
                "collection_errors", "exit_code"):
        if type(value[key]) is not int or value[key] < 0:
            return f"native {key} must be a nonnegative integer"
    if value["schema_version"] != 1:
        return "native summary version mismatch"
    selected = value["selected"]
    if (not isinstance(selected, list) or len(selected) != EXPECTED_COUNT
            or value["selected_count"] != EXPECTED_COUNT
            or not all(isinstance(item, str) and item for item in selected)
            or len(set(selected)) != EXPECTED_COUNT
            or set(selected) != set(EXPECTED_NODEIDS)):
        return "native selected test count/identity mismatch"
    if value["collection_errors"] or value["exit_code"]:
        return "native collection or pytest exit failure"
    if value["duplicate_reports"] != []:
        return "native duplicate test-phase reports"
    reports = value["reports"]
    if not isinstance(reports, dict) or set(reports) != set(selected):
        return "native missing or extra reports"
    complete = {phase: "passed" for phase in ("setup", "call", "teardown")}
    if any(phases != complete for phases in reports.values()):
        return "native failed, skipped, or incomplete test phase"
    return None


def validate_limits(limits, timeout):
    """Reject invalid controls before starting any child."""
    if (type(timeout) not in (int, float) or not math.isfinite(timeout)
            or timeout <= 0):
        raise ValueError("native timeout must be positive and finite")
    for key in ("max_output_bytes", "address_space_bytes"):
        if type(limits.get(key)) is not int or limits[key] <= 0:
            raise ValueError(f"native {key} must be a positive integer")


def native_environment(writable):
    """Build an allowlisted environment without inherited pytest/Python options."""
    writable = Path(writable)
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(writable),
           "TMPDIR": str(writable), "LANG": "C.UTF-8", "PYTHONHASHSEED": "0",
           "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
           "HYPOTHESIS_STORAGE_DIRECTORY": str(writable / "hypothesis"), **THREADS}
    env.update({name: os.environ[name] for name in CONTEXT_ENV if name in os.environ})
    return env


def termination_outcome(exit_code, timed_out):
    """Do not infer a submission timeout from an unexplained external kill."""
    if timed_out:
        return "failed", "native worker exceeded its observed deadline"
    if exit_code == -signal.SIGKILL:
        return "verifier_invalid", "native worker ended by unattributed SIGKILL"
    return None


WORKER_CODE = r'''
"""Staged public native assertions; no private oracle or reward authority."""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import types

# Resolve trusted installed dependencies before adding candidate source.
# Task: import heavy third-party deps here so they resolve from site-packages.
import pytest
import numpy
import scipy
import pandas
import hashlib

source, driver, arguments = sys.argv[1], Path(sys.argv[2]), json.loads(sys.argv[3])
# Task: if hypothesis is used, keep it deterministic:
# from hypothesis import settings
# settings.register_profile("afterquery_native", database=None, derandomize=True)
# settings.load_profile("afterquery_native")

class Reports:
    def __init__(self):
        self.selected = []
        self.deselected_count = 0
        self.collection_errors = 0
        self.reports = {}
        self.duplicate_reports = []

    def pytest_collection_finish(self, session):
        self.selected = [item.nodeid for item in session.items]

    def pytest_deselected(self, items):
        self.deselected_count += len(items)

    def pytest_collectreport(self, report):
        if report.failed:
            self.collection_errors += 1

    def pytest_runtest_logreport(self, report):
        phases = self.reports.setdefault(report.nodeid, {})
        if report.when in phases:
            self.duplicate_reports.append([report.nodeid, report.when])
        phases[report.when] = report.outcome

collector = Reports()
with contextlib.redirect_stdout(sys.stderr):
    sys.path.insert(0, source)
    # Task: import the package under test here (resolves from `source`).
    # If tests import repo helper modules (e.g. tests/helpers.py), load them from
    # `driver` with importlib like the pyjanitor adapter did for strategies.py.
    # If they need conftest fixtures, load that conftest from `driver` and pass it
    # in plugins=[collector, conftest_module]; --noconftest stays on.
    root = Path(source).resolve()
    pins = {'statsmodels/tsa/vector_ar/tests/test_vecm.py': 'd637873312f3977fcc6f3cfbd9c1e88fd6752c071dbc12f824013e8f42ec0bdc', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/parse_jmulti_vecm_output.py': 'c12c51194b6e667230fd3cf7a7e84b4dfc4764ba8cc27b34253f4979b95a3bfc', 'statsmodels/datasets/interest_inflation/data.py': 'ccd5eb64d92435f85bc931c5ce117e2959dc9c24566d0f3fbe817b3d68bbc539', 'statsmodels/datasets/interest_inflation/E6.csv': '458edec09a9f6b91fcc96a1b31f0b889f5f152089c1393d146b82e0ec0b41f3f', 'statsmodels/datasets/interest_inflation/E6_jmulti.csv': '8daa82f188f2193e18cc2c433cf5a3f3fe67443d47bb073c3b90f61a7c44199b', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci.txt': '5c813816649c41c3349823fe164cf7f127e3f756a806aa38f37cac33531e4158', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci_Sigmau.txt': '698254a74f08e5798c782256579526de4bf9a96d1c599774f9eb84e8b2e6621d', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci_diag.txt': 'a9c7c4027f0693fac69224e6dce7c34a5b12cd8045213e82acd2fc218c814a88', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci_fc5.txt': '7824518ed8f5ef15fda47d0b4d70b75477e3afc75feceeca26165cc408cb57c9', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci_granger_causality_dp_r.txt': 'e4c11d93d0a493fb086adedbc64a44d165e57a6da61c3140a4b45bd5e5dcb5c0', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci_granger_causality_r_dp.txt': 'f4256e448d275adfd64f4dd568f8559a74001498629ef30f1bc71c28b7b2e3ba', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci_inst_causality_dp_r.txt': '9286b50a37c05ea109bf5039eca245f4916a9b079ab3fbf73b2f88bc730389d6', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci_inst_causality_r_dp.txt': '5d30c8dee9f491db961603ed5c85c195ec7c0cb27a175314f29ffc7dbc88139c', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci_ir.txt': '6d94432cb03b8b50e6eb4bdd18db48ebf207abf25987c77498b855b003b43fcc', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ci_lagorder.txt': '98d2df7f621c0b9673373962d6768f6a5c517cde147d6b52aa43f3cbd598717b', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili.txt': '0c5230e53eb4f80a1d08664f0b06cccdb111a441774c46c0685242b86cfb90ea', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili_Sigmau.txt': '1950b71cf60e8943538f01d914b7daa3a5efb910fde023084776aa96d81a805f', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili_diag.txt': '88250d7a20968a81958174e07f30d2f129c3a2c9769fe35f27c77714b8cd9908', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili_fc5.txt': '45ae25419b7cd0bf7c4f9b20c7af5056c6fa4554f901fad7678e4c79993748fc', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili_granger_causality_dp_r.txt': 'f84021dcd241cd8a59bfe2c67f660cf22ed1af9966929d5c4862aeeb0017a28c', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili_granger_causality_r_dp.txt': 'e650f528399dc81fd06906ebde92d5c110998c94d3a7cf78703f5ab41ed97fcc', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili_inst_causality_dp_r.txt': 'be57bd777967b585d2708d1e870f38a00ba9e4c93787406ccd61897c9cc1c01e', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili_inst_causality_r_dp.txt': 'df929d0cf38a1df5a780352cfb2114597dbd11e477253eca0f6b0e9e36cf7a53', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili_ir.txt': 'bb5d7700b167128b04f977667288d339de87f42bae64b35db7cf3789b0064ecb', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cili_lagorder.txt': 'e059cd9b24f510db0bb14372f4b11bec554caef6f92846be7f168dc82040c720', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis.txt': '98f136c1c610ed2b35eb937f86d528a1346792df313456c455b11b658eec182a', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis_Sigmau.txt': '1f0f8d3ba6343bc64b1de66fb3769b762c212ff97d2d30f4366a9afaf18f9b96', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis_diag.txt': 'd018cbd0871a7c93bccd57f53ef2ca07b548740766d944431bb152c6a9025d7d', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis_fc5.txt': '9da119d4ee9a77be7cd567ffb0c4c1334d925e44f9fd9275d66d57c777ebaf78', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis_granger_causality_dp_r.txt': '9ba7b5b1a97124d16a01ca9921b766b8f2bf995761f7f4d5a4776df91868353d', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis_granger_causality_r_dp.txt': '1f6cea6837e5ed5aac345cb661c283b28098dfd4bc454bc32f125433342c6e00', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis_inst_causality_dp_r.txt': '87869a352b5d4e61d3800daff3cb3756286430af9f546ceb130477e8184c4e9d', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis_inst_causality_r_dp.txt': '226296c10b1431b8db676011552887e8380098b628423c330159ef6036cc3d7e', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis_ir.txt': '0cf137da97ad0151335e03a4252c614ca423ceebb129a9e24bfe7f5ab00078ea', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cis_lagorder.txt': '92176870009a3e76e31defada109994ca4c7d3193e7e81d981971a80e7001eb2', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli.txt': '6e01a51e7ca7abc34239045a4704b8dfb068438ae45c3841643ea72a6d9928c9', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli_Sigmau.txt': '48de712418abc2ab3acbe18a23cbbb0d1268cdbfeacbee597acba5da28b12eec', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli_diag.txt': '19dc7d1c804799eea07991c77db2cef3c2c98c4b21697c94ae904e8218e3037b', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli_fc5.txt': '840a8cbf8bf517cfbf7b707fd70b1b79d6558c3413457dafdd407cb98e74332a', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli_granger_causality_dp_r.txt': 'ac0765b085eac88fc58078c35a91f5c72eebbdf5a90c5bc8675fb6ac558cd3ed', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli_granger_causality_r_dp.txt': '495585b2d49e178b37106449ffa4cf14068afcbaef49c1ba054c30f8f8cf7d73', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli_inst_causality_dp_r.txt': '9321271db9fead1f0fadf496df9cca5bbf033335c2d8ac42c6aa4364a3517dc6', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli_inst_causality_r_dp.txt': '39256c7fd77b9d928e973850e1ed3f9b1fa55c4ad15a0da18a513f712bcf27b6', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli_ir.txt': 'dcf27c2a3d88d7edaef58c5e339b017b7860946892908e598728ccb8b68aa283', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cisli_lagorder.txt': '0a9273acaaba51c525861932014b73b58a6377b48c96ca40e310e8134f0f1647', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co.txt': 'e9f745a6030cf6f36df28d23ad204220117667bca56f9ff6e7867711844502d5', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co_Sigmau.txt': '2176334cc8515203e462f2c35b18581b64c26e8f2809e65ec4e15c04092d2baa', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co_diag.txt': 'cfec6326f7d5103d090957845cc96e7d96410b025a58c63ad3179ae7f77cac82', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co_fc5.txt': 'd08d8fa47e11d04802406e24faf5cd160ffbb02e6eed90ce44c3e19dadd23fc2', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co_granger_causality_dp_r.txt': 'f22e7243fac42a9f8801fea0c0e3dddc8d5e872069f7c1d6d9129d1567a885e1', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co_granger_causality_r_dp.txt': '5d93e241c7dfd7c7c0555be5540e03d4b0d05fd49a3707c980b7638886a34527', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co_inst_causality_dp_r.txt': '2b9924e59c553b2f1f6e058d2824e6fb024384d355017be6465a2697653607c1', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co_inst_causality_r_dp.txt': 'e44817a74850ddb6722097b1120e9aacdca4ffd1f467812aa07bb9fde501e85b', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co_ir.txt': 'aa10dfd176e4dfa926a0cfd1bc91cd33c507a4088e19ad4dcb20657c1a30bb58', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_co_lagorder.txt': '0fab53931bfca202a6e50015b1168569dd19f13a3be147c150f674f73eccb0e3', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo.txt': '1deccb32790864a34d47fde6a1511383bd80f3423092b1f8d402bb7f0d5609de', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo_Sigmau.txt': '63d57fcffaefc090e30cad4ec1e20271d6e1e90078f0009c49ee04af96ca7839', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo_diag.txt': 'c7d23afb8bf8c4a5af57166984a165657516d210707e6a6bd0d278e453507325', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo_fc5.txt': 'bd6f7f4fc7509dcee0bc5bcf3e4e3a86c3fe27467989e09ee6be67b23aa73180', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo_granger_causality_dp_r.txt': 'ce749edba273aa885a7aca981eade2c751e0573d96911d02b2b431c22b21449f', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo_granger_causality_r_dp.txt': '98f5995e136044e06d44fc214f2593fc75046a5ba22fbfeb9d97afce40b4513b', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo_inst_causality_dp_r.txt': 'd8a5c62cfdaac233756be95125453bd08cba7c209284d0502bacd2a86e7b788f', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo_inst_causality_r_dp.txt': '63c056fd5272afb9ae73d6fec18bc61b426775d9e3f7d6ab588db7f31fe4673d', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo_ir.txt': 'c3537e62e9a98bb511f421c80e0da8431226d2755d66febab9d57424d2f5659a', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_colo_lagorder.txt': '732502b261c039d19d7e7f8dd57d512c353fee8963f5c70e20de019d6b43e781', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos.txt': 'c3d830c36304caad60143227c4e4e6443efa978bf4bbd9f7888a80ae7ea6ddf3', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos_Sigmau.txt': '74ed196010d4867d7f963ce3724114d8b52f26ee4bb73bf988c1c08dc85343f8', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos_diag.txt': 'cebe61c9106c16699f2e2339bc21855e3e45497a5606e92179730311f801ed91', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos_fc5.txt': 'eb2e74a8053719d4524289d8ab7a6068a5f0184164b19d248d11205be01e9148', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos_granger_causality_dp_r.txt': '5e23aa2a5dd52a9a8f27f1aff62f85fc378fb392ba3e1f1915a18c98a931c257', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos_granger_causality_r_dp.txt': '07ed3c3fcd2b91e6c00aea5fac011f0b7f49434fe46005acd949d75733213792', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos_inst_causality_dp_r.txt': 'd79bc78b225ad3a386db5b6bdac55e137d0f3a7034e0c6e6ad9edecd752bb230', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos_inst_causality_r_dp.txt': 'f2e5ef5d4e7fd3ab62cef3861dcc0fd6103a6c6a3a32939056cbb2ffa475e88d', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos_ir.txt': 'e5c6f43f251a2b2376163901779e5243406ddd0633bd691cae4e266fcf9ac83e', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_cos_lagorder.txt': '599b27865bb269ad40888a63d3e07741391cf5579a2a59dcac6c2efbcfb2205a', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo.txt': 'eed81335e70594db4004a66c2ab295b8d0574307750a109095e96189ad9b6977', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo_Sigmau.txt': 'd75e584ec53df0c8d5ca064b8cf4e8c827b509bcdf4792b3269d3928619c413f', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo_diag.txt': 'ef833e980f57fb52f01a89a67d0967e4c078347f0130da0f9ee7279924eea567', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo_fc5.txt': '46c2b89ae4513d46a9b3f897906f466600b63026f47d74a659347373c21709bb', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo_granger_causality_dp_r.txt': '779a6a6c0255729d337fb2c69637fb7977882a05b27818195397443c13832736', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo_granger_causality_r_dp.txt': '3fbd55cf1c7d84f0343f2919d6b9c72196f0f66e3c3d93a24c7c0644c2403ad0', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo_inst_causality_dp_r.txt': '77a8034e26996faffd4c5c45b7861ecc9149b525071593b49e36f2e074e8ead7', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo_inst_causality_r_dp.txt': '908911318cb4bdab4efb1b3f5d0ae7e9a8dc69abc5b3a15d405e1dfbff9440aa', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo_ir.txt': '0f11b2aebd9f7ca06a32a20ee4a30325cddacbce26e0a715eacf35cbeb5b2167', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_coslo_lagorder.txt': '42562ea18a375d024bd2c4a47e390da479de9bd257049642d7f28c343278c177', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc.txt': '9a9ba9381844f906caeb84c56fdc7102db3977cc9f73e96ba9995e9ad16a1664', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc_Sigmau.txt': 'f87ac093a0ec8d528bec3c3aed041874cc8160582047441dd3a737675ff48f70', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc_diag.txt': '34ea117d253164244819187ae7e04e803b3b723939cfb1f92da9e9cb92062fce', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc_fc5.txt': 'f05c22faffb07fc21382f8d5250a37e85898927891d1cda13fee141dff051ef6', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc_granger_causality_dp_r.txt': '466c65532e2b170eaf3a713dd475b6038d4553d26d61cce8e1ce33278c989557', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc_granger_causality_r_dp.txt': '5da59fbcc3f00152e7c487bc09e48b6e83c0eacd8c4a4c3762c2d376844679e9', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc_inst_causality_dp_r.txt': '29629d3dac02fa383d2e0b693eaad416bd1bd9048f1255225349ec42b95b3b69', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc_inst_causality_r_dp.txt': 'ae03ab820e4814a8011fabf47e7e768be8a1c89879f3f2468b88f7ce1669ee3f', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc_ir.txt': 'cff6601e78965f4041ff783af1b7ef3c578313f9a46d852d69645f4aff7c328e', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_nc_lagorder.txt': '749c2bde08b241fe5032c98a0450b114bff590fcfab5271b5378c6447f8a6573', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs.txt': 'b441795841d486158f1c57c8752159166a2cc1c2b36a3ea9848b484883ed2f66', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs_Sigmau.txt': '253c1d3b5f909dd20a84caa616ed46a130ad6b63ea2e40277a6852a21ae8e34e', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs_diag.txt': '074128b7dbcc6e84ddb9427e7b3c6ac61d7eac220783b56cf4722d7e7347e36a', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs_fc5.txt': 'ac15d24092d38de3011552dbc23a78b9b4bb56913939412873a10a4c794b7259', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs_granger_causality_dp_r.txt': '2c461b49044dda57f28d70c53622b3401ff4880e3c776a10276c7e80be9401e1', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs_granger_causality_r_dp.txt': 'd83fbf749f65e2e002fba7822b198827157d91bd700068be68d50aaffb22f256', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs_inst_causality_dp_r.txt': '01bdfe46f06e2a5e2a32d5a71876c64f6013fbb0558d051790cc84d31b48a119', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs_inst_causality_r_dp.txt': 'bb57263f24f29c0a9e2f8552f0703bbaebdabce9c1df630a2d3a89733dcd1615', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs_ir.txt': '68335fc7e41e9fb04e48e4983ccb9d5fcd94cdd79ac6f12593ad88e8d3740b49', 'statsmodels/tsa/vector_ar/tests/JMulTi_results/vecm_e6_jmulti_ncs_lagorder.txt': '5f6029b85a696289bb3bf56838e7f107023969a0777c4f2dfc071938cadd2d0c'}
    # Candidate native helper/data bytes are an immutable selected input, not
    # candidate assertions. They must match the protected BASE/reference bytes.
    for relative, expected_hash in pins.items():
        actual_file = root / relative
        assert hashlib.sha256(actual_file.read_bytes()).hexdigest() == expected_hash, relative
    import statsmodels.tsa.vector_ar.vecm as target
    assert Path(target.__file__).resolve() == root / "statsmodels/tsa/vector_ar/vecm.py"
    exit_code = int(pytest.main(arguments, plugins=[collector]))
    modules = {name: str(Path(module.__file__).resolve()) for name,module in sys.modules.items()
               if name.startswith("statsmodels") and getattr(module,"__file__",None)}
    assert all(Path(path).is_relative_to(root) for path in modules.values()), modules
    assert not any(Path(path).suffix in {".so",".pyd",".dylib"} for path in modules.values()), modules
    print(json.dumps({"kind":"scoped_native_source_closure","statsmodels_modules":modules,
                      "compiled_project_modules":0},sort_keys=True),file=sys.stderr)

print(json.dumps({
    "schema_version": 1, "selected": collector.selected,
    "selected_count": len(collector.selected),
    "deselected_count": collector.deselected_count,
    "collection_errors": collector.collection_errors,
    "exit_code": exit_code, "reports": collector.reports,
    "duplicate_reports": collector.duplicate_reports,
}, sort_keys=True, allow_nan=False))
sys.exit(exit_code)
'''


def _stage(upstream, driver, manifest):
    """Copy exactly pinned public assertions into a root-owned read-only driver."""
    driver.mkdir(mode=0o755)
    for relative, expected in manifest["files"].items():
        data = (Path(upstream) / relative).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise NativeSourceError("protected native input changed during staging")
        target = driver / Path(relative).name
        target.write_bytes(data)
        target.chmod(0o444)
    (driver / "bootstrap.py").write_text(WORKER_CODE)
    (driver / "pytest.ini").write_text(
        "[pytest]\naddopts =\nmarkers =\n"  # Task: register upstream markers if any
    )
    for path in driver.iterdir():
        path.chmod(0o444)
    driver.chmod(0o555)


def run_native(python, source, upstream, scratch, role, limits, timeout):
    """Run the pinned selection on a role's already immutable source snapshot.

    Caller owns the cumulative deadline and accounts returned wall_seconds; this
    function enforces the passed remaining timeout, process limits and cleanup.
    It requires root in Linux, like execute.run_worker. Never install candidate
    code or call it in the parent. Failures of a baseline role invalidate the
    enclosing comparison; that decision belongs to the caller.
    """
    record = {
        "mode": "protected_upstream", "outcome": "verifier_invalid",
        "reason": None, "role": role, "expected_count": EXPECTED_COUNT,
        "collected_count": None, "passed_count": 0, "wall_seconds": 0.0,
        "cpu_seconds": 0.0, "exit_code": None, "timeout": False,
        "timeout_seconds_effective": timeout, "protected_inputs": None,
        "stdout_path": None, "stderr_path": None,
        "stdout_sha256": None, "stderr_sha256": None,
        "uid_quiescence": None,
        "claim_limit": "supplementary native regression, not adversarial proof",
    }
    try:
        validate_limits(limits, timeout)
        if role not in ("candidate", "baseline"):
            raise ValueError("native role must be candidate or baseline")
        if sys.platform != "linux" or os.geteuid() != 0:
            raise ValueError("native gate requires root-owned Linux isolation")
        source = Path(source)
        if source.is_symlink() or not source.is_dir():
            raise ValueError("native source must be the real snapshot directory")
        source = source.resolve(strict=True)
        manifest = selection_manifest(upstream)
        record["protected_inputs"] = manifest
        uid = 10001 if role == "candidate" else 10002
        record["uid"] = uid
        before = quiesce((uid,))
        record["pre_uid_quiescence"] = before
        if before.get("quiescent") is not True:
            raise ValueError("native UID was not quiescent before start")
        scratch = Path(scratch).absolute()
        scratch.mkdir(mode=0o711)
        scratch.chmod(0o711)  # Explicit public traversal despite the private entrypoint umask.
        driver, writable = scratch / "driver", scratch / "writable"
        _stage(upstream, driver, manifest)
        writable.mkdir(mode=0o700)
        os.chown(writable, uid, uid)
    except (OSError, ValueError) as exc:
        record["reason"] = str(exc)
        return record

    command = [str(python), "-I", "-B", str(driver / "bootstrap.py"),
               str(source), str(driver), json.dumps(pytest_arguments(driver))]
    env = native_environment(writable)

    def demote():
        os.umask(0o077)
        if hasattr(os, "sched_getaffinity"):
            os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
        cpu = max(1, math.ceil(timeout))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE,
                           (limits["max_output_bytes"], limits["max_output_bytes"]))
        resource.setrlimit(resource.RLIMIT_AS,
                           (limits["address_space_bytes"], limits["address_space_bytes"]))
        os.setgroups([])
        os.setgid(uid)
        os.setuid(uid)
        resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))

    stdout_path, stderr_path = scratch / "stdout.json", scratch / "stderr.log"
    record.update(stdout_path=str(stdout_path), stderr_path=str(stderr_path))
    start = time.monotonic()
    proc = None
    try:
        with stdout_path.open("xb") as out, stderr_path.open("xb") as err:
            proc = subprocess.Popen(command, cwd=writable, env=env, stdout=out,
                                    stderr=err, preexec_fn=demote, start_new_session=True)
            while True:
                waited, status, usage = os.wait4(proc.pid, os.WNOHANG)
                if waited:
                    break
                if time.monotonic() - start >= timeout:
                    record["timeout"] = True
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    _, status, usage = os.wait4(proc.pid, 0)
                    break
                time.sleep(0.002)
            proc.returncode = os.waitstatus_to_exitcode(status)
            record.update(exit_code=proc.returncode,
                          cpu_seconds=usage.ru_utime + usage.ru_stime)
    except (OSError, subprocess.SubprocessError) as exc:
        record["reason"] = f"native worker launch/wait error: {exc}"
    finally:
        record["wall_seconds"] = time.monotonic() - start
        residual = False
        if proc is not None:
            try:
                os.killpg(proc.pid, 0)
                residual = True
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if proc.returncode is None:
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    record["reason"] = "native process could not be reaped after cleanup"
        quiet = quiesce((uid,))
        record["uid_quiescence"] = quiet
        record["surviving_process"] = residual or bool(quiet["initial_pids"])

    for label, path in (("stdout", stdout_path), ("stderr", stderr_path)):
        if path.is_file():
            record[f"{label}_sha256"] = digest(path)
    if record["reason"]:
        return record
    if quiet.get("quiescent") is not True:
        record["reason"] = "native worker UID did not quiesce"
        return record
    termination = termination_outcome(record["exit_code"], record["timeout"])
    if termination is not None:
        record["outcome"], record["reason"] = termination
        return record
    record["outcome"] = "failed"
    if record["surviving_process"]:
        record["reason"] = "native worker left a surviving process"
        return record
    try:
        info = stdout_path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
                or info.st_size > limits["max_output_bytes"]):
            raise ValueError("native stdout is not a bounded root-owned regular stream")
        summary = strict_json(stdout_path.read_text())
        record["native_summary"] = summary
        reason = validate_summary(summary)
        if isinstance(summary, dict):
            count = summary.get("selected_count")
            if type(count) is int and count >= 0:
                record["collected_count"] = count
            reports = summary.get("reports")
            if isinstance(reports, dict):
                record["passed_count"] = sum(
                    isinstance(phases, dict) and phases.get("call") == "passed"
                    for phases in reports.values())
        if reason:
            raise ValueError(reason)
        if record["exit_code"] != 0:
            raise ValueError("native process exit disagrees with passing summary")
    except (OSError, UnicodeError, ValueError) as exc:
        record["reason"] = str(exc)
        return record
    record.update(outcome="passed", reason=None)
    return record
