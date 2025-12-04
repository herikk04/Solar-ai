import setuptools

setuptools.setup(
    name='solar-panel-pipeline',
    version='1.0',
    install_requires=[
        'apache-beam[gcp]',
        'google-cloud-storage',
        'google-cloud-aiplatform',
        'Pillow',
        'numpy',
        'requests'
    ],
    packages=setuptools.find_packages(),
)