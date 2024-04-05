const languageCodeMap = {
    'English': 'en',
    'Chinese': 'zh',
    'Spanish': 'es',
    'Hindi': 'hi',
    'Korean': 'ko',
    'Japanese': 'ja',
    'Vietnamese': 'vi',
    'Arabic': 'ar',
    'French': 'fr',
    'Russian': 'ru',
    'Portuguese': 'pt',
    'German': 'de',
    'Polish': 'pl',
    'Italian': 'it',
    'Tagalog': 'tl'
};

$(document).ready(function() {
    $('#summarify-btn').click(function(event) {
        event.preventDefault(); // Prevent the default form submission behavior

        const videoUrl = $('#video-url').val();
        const summaryStyle = $('#summary-style').val();
        const languageSelection = $('#language').val();
        const language = languageCodeMap[languageSelection];
        
        // Loading content ID
        $('.loading-content').fadeIn();
        
        // Send an AJAX POST request to the Flask server
        $.ajax({
            url: '/summarize',  // The Flask route
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                'video_url': videoUrl,
                'summary_style': summaryStyle,
                'language': language
            }),
            success: function(response) {
                if (response.message) {
                    // Specific message from the backend (like age-restricted message)
                    $('#message').text(response.message).show();
                } else if (response.transcription) {
                    // Success and there is a transcription
                    $('#summary').text(response.transcription).show();
                }

                // # symbol for element with specific ID, . symbol for element with a specific class
                
                // Hide the loading message after finished loading
                $('.loading-content').fadeOut();

                // Thumbnail image
                /*
                if (response.thumbnail_url) {
                    $('#thumbnail').attr('src', response.thumbnail_url).show();
                } else {
                    $('#thumbnail').hide();
                }
                */
                
                // Embed video
                if (response.embed_video) {
                    var iframeHtml = `<iframe src="${response.embed_video}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>`;
                    $('#video-player-container').html(iframeHtml).show();
                } else {
                    $('#video-player-container').hide();
                }
                
                // Video title
                if (response.title) {
                    $('#video-title').text(response.title).show();
                } else {
                    $('#video-title').hide();
                }

                // Update summary display logic for translated summary
                if (response.transcription) {
                    $('.transcription-window').show();
                    $('#summary').text(response.transcription).show();
                    // Update audio from response structure data
                    if (response.audio) {
                        var audioPlayer = document.getElementById('audio-player');
                        audioPlayer.src = response.audio;
                        audioPlayer.load();

                        $('#play-audio').off('click').on('click', function() {
                            $('#audio-player').get(0).play();
                        });
                
                        $('#pause-audio').off('click').on('click', function() {
                            $('#audio-player').get(0).pause();
                        });

                        $('#play-audio').show();
                        $('#pause-audio').show();
                    }
                } else {
                    $('#summary').text('No translation available.').show();
                    $('.transcription-window').show();
                    $('#play-audio').hide();
                    $('#pause-audio').hide();
                }
                
                // Check for the video URL in the response before attempting to update the video player
                if (response.embed_video) {
                    var iframeHtml = `<iframe src="${response.embed_video}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>`;
                    $('#video-player-container').html(iframeHtml).show();
                }
                
                // Check for the captions in the response before attempting to update the captions
                if (response.captions) {
                    $('#captions').text(response.captions).show();
                } else {
                    $('#captions').text('No captions available.').show();
                }
            },
            error: function(error) {
                // Hide the loading message for error
                $('.loading-content').fadeOut();

                let errorMessage = "Video may be age-restricted, not from YouTube, or another issue occurred. Please check and try again!";

                //! Still not able to recognize as 403, is 500
                if(error.status === 403){
                    // Custom error message for specific status
                    var response = JSON.parse(error.responseText);
                    $('#error-message').text(response.message).show();
                } else {
                    $('#error-message').text("An unexpected error occurred.").show();
                }

                $('#message').text(errorMessage).show();
            }
        });
    });
});
