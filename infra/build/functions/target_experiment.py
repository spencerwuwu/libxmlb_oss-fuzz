# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
################################################################################
"""Script to run target experiments on GCB."""

import argparse
import logging
import os
import sys

import google.auth

import build_lib
import build_project

JCC_DIR = '/usr/local/bin'


def run_experiment(project_name, target_name, args, output_path, errlog_path,
                   build_output_path, upload_corpus_path, upload_coverage_path,
                   experiment_name, upload_reproducer_path, tags):
  config = build_project.Config(testing=True,
                                test_image_suffix='',
                                repo=build_project.DEFAULT_OSS_FUZZ_REPO,
                                branch=None,
                                parallel=False,
                                upload=False,
                                experiment=True,
                                upload_build_logs=build_output_path)

  try:
    project_yaml, dockerfile_contents = (
        build_project.get_project_data(project_name))
  except FileNotFoundError:
    logging.error('Couldn\'t get project data. Skipping %s.', project_name)
    return

  project = build_project.Project(project_name, project_yaml,
                                  dockerfile_contents)

  # Override sanitizers and engine because we only care about libFuzzer+ASan
  # for benchmarking purposes.
  build_project.set_yaml_defaults(project_yaml)
  project_yaml['sanitizers'] = ['address']
  project_yaml['fuzzing_engines'] = ['libfuzzer']
  project_yaml['architectures'] = ['x86_64']

  # Don't do bad build checks.
  project_yaml['run_tests'] = False

  jcc_env = [
      f'CC={JCC_DIR}/clang-jcc',
      f'CXX={JCC_DIR}/clang++-jcc',
  ]
  steps = build_project.get_build_steps(project_name,
                                        project_yaml,
                                        dockerfile_contents,
                                        config,
                                        additional_env=jcc_env)

  build = build_project.Build('libfuzzer', 'address', 'x86_64')
  local_output_path = '/workspace/output.log'
  local_jcc_err_path = '/workspace/err.log'  # From jcc.go:360.
  local_corpus_path_base = '/workspace/corpus'
  local_corpus_path = os.path.join(local_corpus_path_base, target_name)
  default_target_path = os.path.join(build.out, target_name)
  local_target_dir = os.path.join(build.out, 'target')
  local_corpus_zip_path = '/workspace/corpus/corpus.zip'
  local_artifact_path = os.path.join(build.out, 'artifacts/')
  local_stacktrace_path = os.path.join(build.out, 'stacktrace/')
  fuzzer_args = ' '.join(args + [f'-artifact_prefix={local_artifact_path}'])

  # Upload JCC's err.log.
  if errlog_path:
    compile_step_index = -1
    for i, step in enumerate(steps):
      step_args = step.get('args', [])
      if '&& compile' in ' '.join(step_args):
        compile_step_index = i
        break
    if compile_step_index == -1:
      print('Cannot find compile step.')
    else:
      # Insert the upload step right after compile step.
      upload_jcc_err_step = {
          'name':
              'gcr.io/cloud-builders/gsutil',
          'entrypoint':
              '/bin/bash',
          'args': [
              '-c',
              (f'test -f {local_jcc_err_path} || '
               f'echo "Failed to generate JCC error log." | '
               f'tee -a {local_jcc_err_path} && '
               f'gsutil cp {local_jcc_err_path} {errlog_path}'),
          ]
      }
      steps.insert(compile_step_index + 1, upload_jcc_err_step)

  env = build_project.get_env(project_yaml['language'], build)
  env.append('RUN_FUZZER_MODE=batch')
  env.append('CORPUS_DIR=' + local_corpus_path)

  run_step = {
      'name':
          'gcr.io/oss-fuzz-base/base-runner',
      'env':
          env,
      'args': [
          'bash',
          '-c',
          (f'mkdir -p {local_corpus_path} && '
           f'mkdir -p {local_target_dir} && '
           f'mkdir -p {local_artifact_path} && '
           f'mkdir -p {local_stacktrace_path} && '
           f'run_fuzzer {target_name} {fuzzer_args} '
           f'|& tee {local_output_path} || true'),
      ]
  }
  steps.append(build_lib.dockerify_run_step(run_step, build))
  steps.append({
      'name': 'gcr.io/cloud-builders/gsutil',
      'args': ['-m', 'cp', local_output_path, output_path]
  })

  # Upload corpus.
  steps.append({
      'name':
          'gcr.io/cloud-builders/gsutil',
      'entrypoint':
          '/bin/bash',
      'args': [
          '-c',
          (f'cd {local_corpus_path} && '
           f'zip -r {local_corpus_zip_path} * && '
           f'gsutil -m cp {local_corpus_zip_path} {upload_corpus_path} || '
           f'rm -f {local_corpus_zip_path}'),
      ],
  })

  if upload_reproducer_path:
    # Upload binary. First copy the binary directly from default_target_path,
    # if that fails, find it under build out dir and copy to local_target_dir.
    # If either succeeds, then upload it to bucket.
    # If multiple files are found, suffix them and upload them all.
    steps.append({
        'name':
            'gcr.io/cloud-builders/gsutil',
        'entrypoint':
            '/bin/bash',
        'args': [
            '-c',
            (f'cp {default_target_path} {local_target_dir} 2>/dev/null || '
             f'find {build.out} -type f -name {target_name} -exec bash -c '
             f'\'cp "$0" "{local_target_dir}/$(echo "$0" | sed "s@/@_@g")"\' '
             f'{{}} \\; && gsutil cp -r {local_target_dir} '
             f'{upload_reproducer_path}/target_binary || true'),
        ],
    })

    # Upload reproducer.
    steps.append({
        'name':
            'gcr.io/cloud-builders/gsutil',
        'entrypoint':
            '/bin/bash',
        'args': [
            '-c',
            (f'gsutil -m cp -r {local_artifact_path} {upload_reproducer_path} '
             '|| true'),
        ],
    })

    # Upload stacktrace.
    steps.append({
        'name':
            'gcr.io/cloud-builders/gsutil',
        'entrypoint':
            '/bin/bash',
        'args': [
            '-c',
            (f'if [ -f {local_target_dir}/{target_name} ]; then '
             f'{local_target_dir}/{target_name} {local_artifact_path}/* > '
             f'{local_stacktrace_path}/{target_name}.st 2>&1; '
             'else '
             f'for target in {local_target_dir}/*; do '
             f'"$target" {local_artifact_path}/* > '
             f'"{local_stacktrace_path}/$target.st" 2>&1; '
             'done; fi; '
             f'gsutil -m cp -r {local_stacktrace_path} {upload_reproducer_path}'
             ' || true'),
        ],
    })

  # Build for coverage.
  build = build_project.Build('libfuzzer', 'coverage', 'x86_64')
  env = build_project.get_env(project_yaml['language'], build)
  env.extend(jcc_env)

  steps.append(
      build_project.get_compile_step(project, build, env, config.parallel))

  # Generate coverage report.
  env.extend([
      # The coverage script automatically adds the target name to this.
      'CORPUS_DIR=' + local_corpus_path_base,
      'HTTP_PORT=',
      f'COVERAGE_EXTRA_ARGS={project.coverage_extra_args.strip()}',
  ])
  steps.append({
      'name':
          build_lib.get_runner_image_name(''),
      'env':
          env,
      'entrypoint':
          '/bin/bash',
      'args': [
          '-c',
          (
              f'timeout 30m coverage {target_name}; ret=$?; '
              '[ $ret -eq 124 ] '  # Exit code 124 indicates a time out.
              f'&& echo "coverage {target_name} timed out after 30 minutes" '
              f'|| echo "coverage {target_name} completed with exit code $ret"'
          ),
      ],
  })

  # Upload raw coverage data.
  steps.append({
      'name':
          'gcr.io/cloud-builders/gsutil',
      'args': [
          '-m',
          'cp',
          '-r',
          os.path.join(build.out, 'dumps'),
          os.path.join(upload_coverage_path, 'dumps'),
      ],
  })

  # Upload coverage report.
  steps.append({
      'name':
          'gcr.io/cloud-builders/gsutil',
      'args': [
          '-m',
          'cp',
          '-r',
          os.path.join(build.out, 'report'),
          os.path.join(upload_coverage_path, 'report'),
      ],
  })

  # Upload textcovs.
  steps.append({
      'name':
          'gcr.io/cloud-builders/gsutil',
      'args': [
          '-m',
          'cp',
          '-r',
          os.path.join(build.out, 'textcov_reports'),
          os.path.join(upload_coverage_path, 'textcov_reports'),
      ],
  })

  credentials, _ = google.auth.default()
  # Empirically, 3 hours is more than enough for 30-minute fuzzing cloud builds.
  build_lib.BUILD_TIMEOUT = 3 * 60 * 60
  build_id = build_project.run_build(
      project_name,
      steps,
      credentials,
      'experiment',
      experiment=True,
      extra_tags=[experiment_name, project_name] + tags)

  print('Waiting for build', build_id)
  try:
    build_lib.wait_for_build(build_id, credentials, 'oss-fuzz')
  except (KeyboardInterrupt, SystemExit):
    # Cancel the build on exit, to avoid dangling builds.
    build_lib.cancel_build(build_id, credentials, 'oss-fuzz')


def main():
  """Runs a target experiment on GCB."""
  parser = argparse.ArgumentParser(sys.argv[0], description='Test projects')
  parser.add_argument('--project', required=True, help='Project name')
  parser.add_argument('--target', required=True, help='Target name')
  parser.add_argument('args',
                      nargs='+',
                      help='Additional arguments to pass to the target')
  parser.add_argument('--upload_build_log',
                      required=True,
                      help='GCS build log location.')
  parser.add_argument('--upload_err_log',
                      required=False,
                      default='',
                      help='GCS JCC error log location.')
  parser.add_argument('--upload_output_log',
                      required=True,
                      help='GCS log location.')
  parser.add_argument('--upload_corpus',
                      required=True,
                      help='GCS location to upload corpus.')
  parser.add_argument('--upload_reproducer',
                      required=False,
                      default='',
                      help='GCS location to upload reproducer.')
  parser.add_argument('--upload_coverage',
                      required=True,
                      help='GCS location to upload coverage data.')
  parser.add_argument('--experiment_name',
                      required=True,
                      help='Experiment name.')
  parser.add_argument('--tags',
                      nargs='*',
                      help='Tags for cloud build.',
                      default=[])
  args = parser.parse_args()

  run_experiment(args.project, args.target, args.args, args.upload_output_log,
                 args.upload_err_log, args.upload_build_log, args.upload_corpus,
                 args.upload_coverage, args.experiment_name,
                 args.upload_reproducer, args.tags)


if __name__ == '__main__':
  main()
