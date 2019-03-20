from __future__ import print_function, division
import scipy
import tensorflow

from keras.datasets import mnist
from keras_contrib.layers.normalization.instancenormalization import InstanceNormalization
from keras.layers import Input, Dense, Reshape, Flatten, Dropout, Concatenate
from keras.layers import BatchNormalization, Activation, PReLU, Conv2DTranspose
from keras.layers.advanced_activations import LeakyReLU
from keras.layers.convolutional import UpSampling1D, Conv1D
from keras.models import Sequential, Model
from keras.optimizers import Adam
import datetime
import matplotlib.pyplot as plt
import sys
from data_loader import DataLoader
import numpy as np
import os

class Pix2Pix():
    def __init__(self):
        # Input shape
        self.audio_window_length = 16384
        self.audio_feat_dim = 1
        self.audio_shape = (self.audio_window_length,self.audio_feat_dim)

        # Configure data loader
        self.dataset_name = 'NB Tale'
        self.data_loader = DataLoader(dataset_name=self.dataset_name)


        # Calculate output shape of D (PatchGAN)
        #patch = int(self.audio_rows / 2**4)
        #self.disc_patch = (patch, patch, 1)

        # Opts (kan evt flyttes til main)
        self.filter_length = 31
        self.strides = 2
        self.padding = 'same'
        self.use_bias= True
        self.generator_num_kernels_enc = [16, 32, 32, 64, 64, 128, 128, 256, 256, 512, 1024]
        self.generator_num_kernels_dec = self.generator_num_kernels_enc[:-1][::-1] + [1]
        self.discriminator_num_kernels = [16, 32, 32, 64, 64, 128, 128, 256, 256, 512, 1024]


        optimizer = Adam(0.0002, 0.5)

        # Build and compile the discriminator
        self.discriminator = self.build_discriminator()
        self.discriminator.compile(loss='mse',
            optimizer=optimizer,
            metrics=['accuracy'])

        #-------------------------
        # Construct Computational
        #   Graph of Generator
        #-------------------------

        # Build the generator
        self.generator = self.build_generator()

        # Input images and their conditioning images
        audio_A = Input(shape=self.audio_shape)
        audio_B = Input(shape=self.audio_shape)

        # By conditioning on B generate a fake version of A
        fake_A = self.generator(audio_B)

        # For the combined model we will only train the generator
        self.discriminator.trainable = False

        # Discriminators determines validity of translated images / condition pairs
        valid = self.discriminator([fake_A, audio_B])

        self.combined = Model(inputs=[audio_A, audio_B], outputs=[valid, fake_A])
        self.combined.compile(loss=['mse', 'mae'],
                              loss_weights=[1, 100],
                              optimizer=optimizer)

    def build_generator(self):
        """Inspired by the SEGAN setup"""

        # Define the encoder
        for layer, numkernels in enumerate(self.generator_num_kernels_enc):
            encoder_out = Conv1D(numkernels,self.filter_length,strides=self.strides,padding=self.padding,use_bias=self.use_bias)(encoder_out)

            # Skip connections
            if layer < len(self.generator_num_kernels_enc)-1:
                skips.append(encoder_out)

            #Apply PReLU
            encoder_out = PReLU(alpha_initializer = 'zero', weigths=None)(encoder_out)
        
        
        # Add intermediate noise layer (why?)
        z_dim = (8,1024)
        z = Input(shape = z_dim ,name = 'noise_input')
        decoder_out = keras.layers.concatenate([encoder_out,z]) 

        # Define the decoder
        for layer, numkernels in enumerate(self.generator_num_kernels_dec):
            dim_in = decoder_out.get_shape().as_list()
            # The conv2dtranspose needs 3D input
            new_shape = (dim_in[1],1, dim_in[2])
            decoder_out = Reshape(new_shape)(decoder_out)   
            decoder_out = Conv2DTranspose(self.generator_num_kernels_dec,[self.filter_length,1],strides=[strides,1],padding = self.padding, use_bias = self.use_bias)(decoder_out)
            # Reshape back to 2D
            n_rows = strides*z_dim[0]
            n_cols = self.discriminator_num_kernels
            decoder_out.set_shape([None, n_rows,1,n_cols])
            new_shape = (n_rows,n_cols)

            decoder_out = Reshape(new_shape)(decoder_out)

            # PRelu
            decoder_out = PReLU(alpha_initializer = 'zero', weights=None)(decoder_out)
            # Skip connections
            skip_ = skips[-(layer+1)]
            decoder_out = keras.layer.concatenate([decoder_out,skip_])

            # Create the model 
            G = Model(inputs = [self.audio_shape], outputs = [decoder_out])


            # Show summary
            G.summary()

            return G
    def build_discriminator(self):
        audio_in_clean = Input(shape=self.audio_shape, name = 'in_clean')
        audio_in_mixed = Input(shape=self.audio_shape, name = 'in_mixed')

        discriminator_out = keras.layers.concatenate([audio_in_clean,audio_in_mixed])

        for layer, numkernels in enumerate(self.discriminator_num_kernels):
            discriminator_out = Conv1D(numkernels,self.filter_length,strides=self.strides,padding=self.padding,use_bias=self.use_bias)(discriminator_out)

            # Apply batch normalization
            discriminator_out = BatchNormalization()(discriminator_out)
            # Apply LeakyReLU
            discriminator_out = LeakyReLU(alpha = 0.3)(discriminator_out)
        
        discriminator_out = Conv1D(1, 1, padding=self.padding, use_bias=self.use_bias, 
                    name='logits_conv')(discrimintor_out)
        discriminator_out = Flatten()(discriminator_out)
        discriminator_out = Dense(1, activation='linear', name='discriminator_output')(discriminator_out)
        D = Model([audio_in_clean, audio_in_mixed], discriminator_out)

        # Trainable?

        D.summary()



        return D

    def train(self, epochs, batch_size=1, sample_interval=50):

        start_time = datetime.datetime.now()

        # Adversarial loss ground truths
        valid = np.ones((batch_size,) + self.disc_patch)
        fake = np.zeros((batch_size,) + self.disc_patch)

        for epoch in range(epochs):
            for batch_i, (audios_A, audios_B) in enumerate(self.data_loader.load_batch(batch_size)):
                print("hellooo")
                # ---------------------
                #  Train Discriminator
                # ---------------------

                # Condition on B and generate a translated version
                fake_A = self.generator.predict(audios_B)

                # Train the discriminators (original images = real / generated = Fake)
                d_loss_real = self.discriminator.train_on_batch([audios_A, audios_B], valid)
                d_loss_fake = self.discriminator.train_on_batch([fake_A, audios_B], fake)
                d_loss = 0.5 * np.add(d_loss_real, d_loss_fake)

                # -----------------
                #  Train Generator
                # -----------------

                # Train the generators
                g_loss = self.combined.train_on_batch([audios_A, audios_B], [valid, audios_A])

                elapsed_time = datetime.datetime.now() - start_time
                print("hey there")
                # Plot the progress
                print ("[Epoch %d/%d] [Batch %d/%d] [D loss: %f, acc: %3d%%] [G loss: %f] time: %s" % (epoch, epochs,
                                                                        batch_i, self.data_loader.n_batches,
                                                                        d_loss[0], 100*d_loss[1],
                                                                        g_loss[0],
                                                                        elapsed_time))

                # If at save interval => save generated image samples
                #if batch_i % sample_interval == 0:
                #    self.sample_images(epoch, batch_i)

    def sample_images(self, epoch, batch_i):
        os.makedirs('images/%s' % self.dataset_name, exist_ok=True)
        r, c = 3, 3

        audios_A, audios_B = self.data_loader.load_data(batch_size=3, is_testing=True)
        fake_A = self.generator.predict(audios_B)

        gen_audios = np.concatenate([audios_B, fake_A, audios_A])

        # Rescale images 0 - 1
        gen_audios = 0.5 * gen_audios + 0.5

        titles = ['Condition', 'Generated', 'Original']
        fig, axs = plt.subplots(r, c)
        cnt = 0
        for i in range(r):
            for j in range(c):
                axs[i,j].imshow(gen_audios[cnt])
                axs[i, j].set_title(titles[i])
                axs[i,j].axis('off')
                cnt += 1
        fig.savefig("images/%s/%d_%d.png" % (self.dataset_name, epoch, batch_i))
        plt.close()


if __name__ == '__main__':
    '''Jeg prøver:
    config = tensorflow.ConfigProto(intra_op_parallelism_threads=0, 
                        inter_op_parallelism_threads=0, 
                        allow_soft_placement=True)

    session = tensorflow.Session(config=config)
    '''

    gan = Pix2Pix()
    gan.train(epochs=1, batch_size=1, sample_interval=200)
